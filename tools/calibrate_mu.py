"""Calibrate μ_eff for the cloud Docker plant (graph_set + graph_quota).

Usage:
    python tools/calibrate_mu.py \
        --hosts http://localhost:8080 http://localhost:8081 \
        --container graph_set --quota-container graph_quota \
        --cores 2 4 8 16 --users 22 --duration 60 \
        --warmup 15 --payload-size 25000

For each core count c, the script:
  1. Sets cpuset_cpus on the "set" container and a matching cpu_quota on the
     "quota" container (replicating controller_loop.py's cgroup logic).
  2. Launches `users` concurrent worker threads that pound /function/graph_mst
     with the canonical payload size (no noise) for `duration` seconds, after
     a `warmup` window that is excluded from statistics.
  3. Reports mean RT, P95 RT, throughput X.
  4. Fits μ_eff per-core using the M/M/c steady-state mean response time:
         W_M/M/c(λ, c, μ) = 1/μ + Erlang-C(c, ρ) / (c·μ·(1-ρ))
     We invert this numerically for μ given measured (W, λ, c).

Output:
  - tools/calibrate_mu_<timestamp>.json   raw measurements
  - stdout: human-readable table + recommended controller `st` (=SLA·μ_eff)

Requires: requests, docker, numpy, scipy.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import docker
import numpy as np
import requests
from scipy.optimize import brentq


CPU_PERIOD = 100000


def erlang_c(c: int, rho: float) -> float:
    """Erlang-C blocking probability for an M/M/c queue with utilization rho<1."""
    if rho >= 1.0:
        return 1.0
    a = c * rho
    sum_terms = sum((a ** k) / math.factorial(k) for k in range(c))
    last = (a ** c) / (math.factorial(c) * (1 - rho))
    return last / (sum_terms + last)


def mmc_mean_response_time(lam: float, c: int, mu: float) -> float:
    rho = lam / (c * mu)
    if rho >= 1.0:
        return float("inf")
    Pq = erlang_c(c, rho)
    Wq = Pq / (c * mu * (1 - rho))
    return 1.0 / mu + Wq


def fit_mu_from_W(W_obs: float, lam: float, c: int, mu_lo: float = 0.1,
                  mu_hi: float = 1000.0) -> float:
    """Numerically solve W_M/M/c(λ, c, μ) = W_obs for μ."""
    f = lambda mu: mmc_mean_response_time(lam, c, mu) - W_obs
    # Need f(lo) > 0 and f(hi) < 0 for brentq
    while f(mu_lo) <= 0 and mu_lo > 1e-4:
        mu_lo /= 2
    while f(mu_hi) >= 0 and mu_hi < 1e6:
        mu_hi *= 2
    return brentq(f, mu_lo, mu_hi)


def set_cores(client, set_name: str, quota_name: str, c: int,
              cpu_range_start: int = 0) -> None:
    """Apply integer + fractional cores to the two containers (mirror controller_loop)."""
    set_int = max(1, int(c))
    quota_frac = max(0.0, c - set_int)
    cset = client.containers.get(set_name)
    cquota = client.containers.get(quota_name)
    cset.update(cpuset_cpus=f"{cpu_range_start}-{cpu_range_start + set_int - 1}")
    cquota.update(cpu_quota=int(max(1, quota_frac * CPU_PERIOD)),
                  cpu_period=CPU_PERIOD)


def worker_loop(host: str, path: str, payload: dict, headers: dict,
                stop_event: threading.Event, latencies: list, started_at: float,
                warmup_s: float) -> None:
    while not stop_event.is_set():
        t0 = time.time()
        try:
            requests.post(host + path, json=payload, headers=headers, timeout=30)
        except requests.RequestException:
            continue
        rt = time.time() - t0
        if (t0 - started_at) >= warmup_s:
            latencies.append(rt)


def measure_at(c: float, args, client) -> dict:
    set_cores(client, args.container, args.quota_container, c, args.cpu_range_start)
    print(f"[calibrate] c={c}  → cpuset configured, sleeping 5s for cgroup settle …")
    time.sleep(5)

    latencies: list[float] = []
    stop_event = threading.Event()
    started_at = time.time()
    payload = {"size": args.payload_size}
    headers = {"Content-Type": "application/json"}

    with ThreadPoolExecutor(max_workers=args.users) as pool:
        futures = [
            pool.submit(worker_loop, args.hosts[0], args.path, payload, headers,
                        stop_event, latencies, started_at, args.warmup)
            for _ in range(args.users)
        ]
        time.sleep(args.warmup + args.duration)
        stop_event.set()
        for f in as_completed(futures):
            f.result()

    if not latencies:
        return {"c": c, "n": 0}

    arr = np.asarray(latencies)
    mean_rt = float(arr.mean())
    p95_rt = float(np.percentile(arr, 95))
    throughput = len(arr) / args.duration
    try:
        mu_fit = fit_mu_from_W(mean_rt, lam=throughput, c=int(round(c)))
    except (ValueError, RuntimeError) as exc:
        mu_fit = None
        print(f"[calibrate] μ fit failed at c={c}: {exc}")
    return {
        "c": c, "n": len(arr),
        "mean_rt": mean_rt, "p95_rt": p95_rt,
        "throughput_X": throughput,
        "mu_fit_per_core": mu_fit,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hosts", nargs="+", required=True)
    p.add_argument("--path", default="/function/graph_mst")
    p.add_argument("--container", default="graph_set")
    p.add_argument("--quota-container", default="graph_quota")
    p.add_argument("--cpu-range-start", type=int, default=0)
    p.add_argument("--cores", nargs="+", type=float, default=[2, 4, 8, 16])
    p.add_argument("--users", type=int, default=22)
    p.add_argument("--duration", type=float, default=60.0,
                   help="seconds of measurement after warmup")
    p.add_argument("--warmup", type=float, default=15.0)
    p.add_argument("--payload-size", type=int, default=25000)
    p.add_argument("--app-sla", type=float, default=0.25,
                   help="Used to recommend `st = SLA · μ_eff`.")
    args = p.parse_args()

    client = docker.from_env()
    results = []
    for c in args.cores:
        r = measure_at(c, args, client)
        print(f"[calibrate] c={c:5}  n={r.get('n', 0):5}  "
              f"mean_RT={r.get('mean_rt', float('nan')):.3f}s  "
              f"p95_RT={r.get('p95_rt', float('nan')):.3f}s  "
              f"X={r.get('throughput_X', float('nan')):.2f} req/s  "
              f"μ_fit={r.get('mu_fit_per_core')}")
        results.append(r)

    out_path = Path("tools") / f"calibrate_mu_{int(time.time())}.json"
    out_path.write_text(json.dumps({"args": vars(args), "results": results}, indent=2))
    print(f"\n[calibrate] raw → {out_path}")

    mu_vals = [r["mu_fit_per_core"] for r in results
               if r.get("mu_fit_per_core") is not None]
    if mu_vals:
        mu_med = statistics.median(mu_vals)
        recommended_st = args.app_sla * mu_med
        print(f"\n[calibrate] median μ_eff/core = {mu_med:.3f} req/s")
        print(f"[calibrate] recommended `st` = SLA·μ_eff = "
              f"{args.app_sla} · {mu_med:.3f} = {recommended_st:.3f}")
    else:
        print("\n[calibrate] no valid μ fits — check workload saturation")


if __name__ == "__main__":
    main()
