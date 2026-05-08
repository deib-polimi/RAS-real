"""Calibrate μ_eff for the cloud Docker plant (graph_set + graph_quota).

Usage:
    python3 tools/calibrate_mu.py \
        --hosts http://localhost:8080 http://localhost:8081 \
        --container graph_set --quota-container graph_quota \
        --cores 2 4 8 16 --users 22 --duration 60 --warmup 15 \
        --payload-size 25000 --app-sla 0.25

For each requested core count `c`, the script:
  1. Applies cpuset_cpus on the "set" container and a matching cpu_quota on
     the "quota" container — exactly mirroring controller_loop.py's cgroup
     layout, with one extra rule: when the fractional component of `c`
     produces a quota below Docker's CFS floor (1000us) we set cpu_quota=-1
     to disable the quota cleanly, instead of leaving stale state.
  2. Spawns `users` concurrent worker threads pounding /function/graph_mst
     with the canonical payload size for `duration` seconds, after a
     `warmup` window that is excluded from statistics. Workers route between
     hosts[0] (set) and hosts[1] (quota) with the same probability rule
     used by request_maker.py: p_set = set_int / (set_int + quota_frac).
  3. Reports mean RT, P95 RT, throughput X.
  4. Fits μ_eff/core via the M/M/c steady-state mean response time, solved
     numerically with a bisection routine (no scipy dependency).

Output:
  - tools/calibrate_mu_<timestamp>.json   raw measurements
  - stdout: human-readable table + recommended `st = SLA · μ_eff`
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import docker


CPU_PERIOD = 100000          # cgroup CFS period (us)
QUOTA_FLOOR_US = 1000        # Docker's hard minimum for cpu_quota


# ---------------------------------------------------------------------------
# cgroup application
# ---------------------------------------------------------------------------

def _apply_cgroup(client, set_name: str, quota_name: str, c: float,
                  cpu_range_start: int = 0):
    """Apply `c` total cores to the two-container layout.

    containerSet     ← cpuset_cpus  (CPU affinity, integer part)
    containerQuotas  ← cpu_quota    (CFS quota, fractional part)

    Docker rejects cpu_quota < 1000us (CFS minimum). When the fractional
    component falls below this floor — including the integer-`c` case where
    it is exactly zero — we explicitly disable the quota with cpu_quota=-1
    rather than leaving stale state from a previous call.

    Returns (set_int, quota_frac) so callers can mirror request_maker's
    routing probability.
    """
    set_int = max(1, int(c))
    quota_frac = max(0.0, c - set_int)
    quota_us = int(round(quota_frac * CPU_PERIOD))

    cset = client.containers.get(set_name)
    cquota = client.containers.get(quota_name)

    cset.update(cpuset_cpus=f"{cpu_range_start}-{cpu_range_start + set_int - 1}")
    if quota_us >= QUOTA_FLOOR_US:
        cquota.update(cpu_quota=quota_us, cpu_period=CPU_PERIOD)
    else:
        cquota.update(cpu_quota=-1)

    return set_int, quota_frac


# ---------------------------------------------------------------------------
# M/M/c steady-state response time + μ inversion (no scipy)
# ---------------------------------------------------------------------------

def erlang_c(c: int, rho: float) -> float:
    """Erlang-C (probability of queueing) for an M/M/c with utilization rho<1."""
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


def _bisect(f, lo: float, hi: float, tol: float = 1e-6,
            max_iter: int = 200) -> float:
    """Pure-Python bisection (no scipy). Requires f(lo)·f(hi) < 0."""
    flo = f(lo)
    fhi = f(hi)
    if flo == 0:
        return lo
    if fhi == 0:
        return hi
    if flo * fhi > 0:
        raise ValueError(f"No sign change in bracket [{lo},{hi}]")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        fmid = f(mid)
        if abs(fmid) < tol or (hi - lo) < tol:
            return mid
        if flo * fmid < 0:
            hi, fhi = mid, fmid
        else:
            lo, flo = mid, fmid
    return 0.5 * (lo + hi)


def fit_mu_from_W(W_obs: float, lam: float, c: int,
                  mu_lo: float = 0.01, mu_hi: float = 10000.0) -> float:
    """Solve W_M/M/c(lam, c, mu) = W_obs for mu by bisection.

    Bracket auto-expands if the initial range does not contain a sign change.
    """
    f = lambda mu: mmc_mean_response_time(lam, c, mu) - W_obs
    while f(mu_lo) <= 0 and mu_lo > 1e-6:
        mu_lo /= 2
    while f(mu_hi) >= 0 and mu_hi < 1e8:
        mu_hi *= 2
    return _bisect(f, mu_lo, mu_hi)


# ---------------------------------------------------------------------------
# Worker / measurement
# ---------------------------------------------------------------------------

def _worker_loop(hosts, path, payload, headers, p_set, stop_event,
                 latencies, started_at, warmup_s, lock):
    """One pseudo-user: keep firing requests until stop_event is set.

    Routes to hosts[0] (set container) with probability p_set, otherwise to
    hosts[1] (quota container) — same rule as request_maker.run().
    """
    import requests
    while not stop_event.is_set():
        host = hosts[0] if random.random() <= p_set else hosts[1]
        t0 = time.time()
        try:
            requests.post(host + path, json=payload, headers=headers, timeout=30)
        except requests.RequestException:
            continue
        rt = time.time() - t0
        if (t0 - started_at) >= warmup_s:
            with lock:
                latencies.append(rt)


def _percentile(values, q: float) -> float:
    """Linear-interpolated percentile (q in [0,100]) without numpy."""
    if not values:
        return float("nan")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = (q / 100.0) * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def measure_at(c: float, args, client) -> dict:
    set_int, quota_frac = _apply_cgroup(
        client, args.container, args.quota_container, c, args.cpu_range_start)
    p_set = set_int / (set_int + quota_frac) if (set_int + quota_frac) > 0 else 1.0

    print(f"[calibrate] c={c}  set_int={set_int}  quota_frac={quota_frac:.3f}  "
          f"p_set={p_set:.3f} → cgroup applied, settling 5s …")
    time.sleep(5)

    latencies: list = []
    lock = threading.Lock()
    stop_event = threading.Event()
    started_at = time.time()
    payload = {"size": args.payload_size}
    headers = {"Content-Type": "application/json"}

    with ThreadPoolExecutor(max_workers=args.users) as pool:
        futures = [
            pool.submit(_worker_loop, args.hosts, args.path, payload, headers,
                        p_set, stop_event, latencies, started_at, args.warmup,
                        lock)
            for _ in range(args.users)
        ]
        time.sleep(args.warmup + args.duration)
        stop_event.set()
        for f in as_completed(futures):
            f.result()

    if not latencies:
        return {"c": c, "n": 0}

    mean_rt = statistics.mean(latencies)
    p95_rt = _percentile(latencies, 95.0)
    throughput = len(latencies) / args.duration
    try:
        mu_fit = fit_mu_from_W(mean_rt, lam=throughput, c=int(round(c)))
        mu_per_core = mu_fit
    except (ValueError, RuntimeError) as exc:
        mu_per_core = None
        print(f"[calibrate] μ fit failed at c={c}: {exc}")

    return {
        "c": c, "n": len(latencies),
        "mean_rt": mean_rt, "p95_rt": p95_rt,
        "throughput_X": throughput,
        "mu_fit_per_core": mu_per_core,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hosts", nargs="+", required=True,
                   help="[set_host quota_host] — same order as controller_loop")
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

    if len(args.hosts) < 2:
        # If only one host given, route everything there.
        args.hosts = [args.hosts[0], args.hosts[0]]

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
