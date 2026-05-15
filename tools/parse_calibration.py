#!/usr/bin/env python3
"""Parse a calibration JSONL log produced by CalibrationController and
produce a per-cores μ̂ estimate plus aggregated recommendations.

Usage:
    python3 tools/parse_calibration.py logs/calibration-YYYYMMDD-HHMMSS.jsonl \\
        [--warmup-s 30] [--noise-scale-target 1.5] [--max-cores 8] [--sla-min-ms 150]

Outputs:
    - stdout: human-readable Markdown report
    - <input>.report.json: machine-readable summary
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import os
from collections import defaultdict
from pathlib import Path


def load_jsonl(path: str):
    rows = []
    with open(path) as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def segment_by_cores(rows, warmup_s: float):
    """Group rows into intervals defined by consecutive equal cores_set,
    dropping the first `warmup_s` of each interval."""
    if not rows:
        return []

    intervals = []
    current = []
    current_cores = rows[0]["cores_set"]
    current_t_start = rows[0]["t"]

    for r in rows:
        if r["cores_set"] != current_cores:
            intervals.append({
                "cores": current_cores,
                "t_start": current_t_start,
                "t_end": current[-1]["t"] if current else current_t_start,
                "rows_raw": current,
            })
            current = []
            current_cores = r["cores_set"]
            current_t_start = r["t"]
        current.append(r)

    if current:
        intervals.append({
            "cores": current_cores,
            "t_start": current_t_start,
            "t_end": current[-1]["t"],
            "rows_raw": current,
        })

    # Apply warmup filter
    for it in intervals:
        t_meas_start = it["t_start"] + warmup_s
        it["rows_measured"] = [r for r in it["rows_raw"] if r["t"] >= t_meas_start]
        it["duration_total"] = it["t_end"] - it["t_start"]
        it["duration_measured"] = (it["rows_measured"][-1]["t"] - it["rows_measured"][0]["t"]
                                   if len(it["rows_measured"]) >= 2 else 0.0)
    return intervals


def stats_for_interval(it):
    rows = it["rows_measured"]
    n = len(rows)
    if n == 0:
        return None
    rt_mean = [r["rt_mean"] for r in rows]
    rt_p95 = [r["rt_p95"] for r in rows]
    throughput = [r["throughput"] for r in rows]
    u_cores = [r["u_cores"] for r in rows]
    users = [r["users"] for r in rows]

    X = statistics.mean(throughput)
    U = statistics.mean(u_cores)
    mu_per_core_util_law = (X / U) if U > 0.01 else float("nan")

    return {
        "cores_set": int(it["cores"]),
        "N_measured": n,
        "duration_measured_s": round(it["duration_measured"], 1),
        "throughput_X": round(X, 3),
        "u_cores_mean": round(U, 3),
        "u_cores_std": round(statistics.stdev(u_cores) if n > 1 else 0.0, 3),
        "users_mean": round(statistics.mean(users), 2),
        "rt_mean_s": round(statistics.mean(rt_mean), 4),
        "rt_p95_s": round(statistics.mean(rt_p95), 4),
        "rt_p95_max_s": round(max(rt_p95), 4),
        "mu_per_core_utilization_law": round(mu_per_core_util_law, 3),
        "rho_estimated": round(X / (it["cores"] * mu_per_core_util_law), 3) if (
            mu_per_core_util_law and not math.isnan(mu_per_core_util_law)
            and mu_per_core_util_law > 0
        ) else None,
    }


def aggregate(per_cores_stats, noise_scale_target: float, max_cores_runtime: int,
              sla_min_ms: float):
    valid = [s for s in per_cores_stats if s and not math.isnan(s["mu_per_core_utilization_law"])]
    if not valid:
        return {"error": "no valid intervals to aggregate"}
    mus = [s["mu_per_core_utilization_law"] for s in valid]
    mu_avg = statistics.mean(mus)
    mu_std = statistics.stdev(mus) if len(mus) > 1 else 0.0

    # Inferred post-drift μ̂ for noise_scale_target on payload
    # noise_type="avg" with noise_scale=σ → payload becomes (1+σ)× → μ_post ≈ μ_pre / (1+σ)
    mu_post = mu_avg / (1.0 + noise_scale_target)

    cap_pre = max_cores_runtime * mu_avg
    cap_post = max_cores_runtime * mu_post

    # SLA recommendation: max(min, 1.5/μ_post) — ensures floor 1/μ_post sotto SLA
    sla_floor_post = 1.0 / mu_post if mu_post > 0 else float("inf")
    sla_proposed_s = max(sla_min_ms / 1000.0, 1.5 * sla_floor_post)
    sla_proposed_ms = sla_proposed_s * 1000

    # Workload range: target ρ_peak post-drift ≤ 0.70 to leave guardrail margin
    lam_max_post_safe = 0.70 * cap_post
    lam_min_useful = 0.20 * cap_post  # avoid trivial under-load
    if lam_min_useful >= lam_max_post_safe:
        lam_min_useful = 0.4 * lam_max_post_safe
    shift = (lam_max_post_safe + lam_min_useful) / 2.0
    mod = (lam_max_post_safe - lam_min_useful) / 2.0

    return {
        "mu_per_core_avg": round(mu_avg, 3),
        "mu_per_core_std": round(mu_std, 3),
        "mu_per_core_cv": round(mu_std / mu_avg, 3) if mu_avg > 0 else None,
        "mu_post_drift_inferred": round(mu_post, 3),
        "noise_scale_assumed_for_post_drift": noise_scale_target,
        "max_cores_runtime": max_cores_runtime,
        "capacity_pre_drift_req_s": round(cap_pre, 1),
        "capacity_post_drift_req_s": round(cap_post, 1),
        "sla_floor_post_drift_s": round(sla_floor_post, 4),
        "sla_proposed_s": round(sla_proposed_s, 3),
        "sla_proposed_ms": round(sla_proposed_ms, 0),
        "workload_lam_min": round(lam_min_useful, 1),
        "workload_lam_max": round(lam_max_post_safe, 1),
        "singen_shift": round(shift, 1),
        "singen_mod": round(mod, 1),
        "singen_period_s_recommended": 360,
    }


def render_markdown(per_cores_stats, aggregated, jsonl_path, args):
    lines = []
    lines.append("# Calibration Report")
    lines.append("")
    lines.append(f"**Input log**: `{jsonl_path}`  ")
    lines.append(f"**Warmup excluded per interval**: {args.warmup_s}s  ")
    lines.append(f"**Max cores at runtime (host detected/specified)**: {args.max_cores}  ")
    lines.append(f"**Drift severity assumed for post-drift extrapolation**: noise_scale={args.noise_scale_target}")
    lines.append("")
    lines.append("## Per-cores measurements")
    lines.append("")
    lines.append("| cores | N | X (req/s) | U (cores used) | mean RT | p95 RT | μ̂/core (X/U) | ρ |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for s in per_cores_stats:
        if not s: continue
        lines.append(f"| {s['cores_set']} | {s['N_measured']} | {s['throughput_X']:.2f} | "
                     f"{s['u_cores_mean']:.2f} | {s['rt_mean_s']*1000:.0f}ms | "
                     f"{s['rt_p95_s']*1000:.0f}ms | {s['mu_per_core_utilization_law']:.2f} | "
                     f"{s['rho_estimated'] if s['rho_estimated'] is not None else '—'} |")
    lines.append("")
    lines.append("## Aggregated")
    lines.append("")
    a = aggregated
    if "error" in a:
        lines.append(f"⚠️ {a['error']}")
        return "\n".join(lines)
    lines.append(f"- **μ̂/core (pre-drift)** = {a['mu_per_core_avg']} req/s/core "
                 f"(std={a['mu_per_core_std']}, CV={a['mu_per_core_cv']})")
    lines.append(f"- **μ̂/core (post-drift inferred, noise×{a['noise_scale_assumed_for_post_drift']})** "
                 f"= {a['mu_post_drift_inferred']} req/s/core")
    lines.append(f"- **Capacity pre-drift @ {a['max_cores_runtime']} cores** = "
                 f"{a['capacity_pre_drift_req_s']} req/s")
    lines.append(f"- **Capacity post-drift @ {a['max_cores_runtime']} cores** = "
                 f"{a['capacity_post_drift_req_s']} req/s")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    lines.append(f"- **SLA proposed**: {a['sla_proposed_ms']:.0f}ms "
                 f"({a['sla_proposed_s']:.3f}s)  ← max(min={args.sla_min_ms}ms, 1.5·1/μ̂_post)")
    lines.append(f"  - Floor post-drift (1/μ̂_post): {a['sla_floor_post_drift_s']*1000:.0f}ms")
    lines.append(f"- **Workload SinGen recommended**:")
    lines.append(f"  - `shift = {a['singen_shift']}`  `mod = {a['singen_mod']}`  "
                 f"`period = {a['singen_period_s_recommended']}`")
    lines.append(f"  - lam ∈ [{a['workload_lam_min']}, {a['workload_lam_max']}] req/s")
    lines.append(f"  - ρ_peak post-drift = {a['workload_lam_max']/a['capacity_post_drift_req_s']:.2f} "
                 f"(target ≤ 0.70 for guardrail margin)")
    lines.append("")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("jsonl_path", help="Path to calibration-*.jsonl log")
    p.add_argument("--warmup-s", type=float, default=30.0,
                   help="Seconds to discard at the start of each cores slot (default 30)")
    p.add_argument("--noise-scale-target", type=float, default=1.5,
                   help="Drift noise_scale used in experiments → infer μ̂_post (default 1.5)")
    p.add_argument("--max-cores", type=int, default=None,
                   help="Cores available on host (default: os.cpu_count())")
    p.add_argument("--sla-min-ms", type=float, default=150.0,
                   help="Minimum SLA floor in ms (default 150)")
    args = p.parse_args()

    if args.max_cores is None:
        args.max_cores = os.cpu_count() or 8

    rows = load_jsonl(args.jsonl_path)
    if not rows:
        print(f"ERROR: no rows parsed from {args.jsonl_path}")
        return

    intervals = segment_by_cores(rows, args.warmup_s)
    per_cores_stats = [stats_for_interval(it) for it in intervals]
    aggregated = aggregate(per_cores_stats, args.noise_scale_target,
                            args.max_cores, args.sla_min_ms)

    md = render_markdown(per_cores_stats, aggregated, args.jsonl_path, args)
    print(md)

    # Save JSON summary
    out_json = Path(args.jsonl_path).with_suffix(".report.json")
    with open(out_json, "w") as fh:
        json.dump({
            "input": args.jsonl_path,
            "warmup_s": args.warmup_s,
            "noise_scale_target": args.noise_scale_target,
            "max_cores": args.max_cores,
            "sla_min_ms": args.sla_min_ms,
            "per_cores": per_cores_stats,
            "aggregated": aggregated,
        }, fh, indent=2)
    print(f"\n→ machine-readable summary: {out_json}")


if __name__ == "__main__":
    main()
