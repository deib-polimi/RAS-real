#!/usr/bin/env python
"""Headline comparison: 3 architectures × 3 scenarios.

Fair head-to-head between
  - PPO solo (frozen pre-trained, argmax action)
  - PPO+PI with anti-windup PI (realistic baseline, no windup pathology)
  - GPPPO (ours) = same anti-windup PI + single GP architectural fix (GP-R2)

across three workload/noise combinations.

Output: a single ASCII table summarising cost, SLA-violation rate, p99 RT,
tail-AUC, and Δ vs each baseline. n=5 seeds, medians reported.

Usage:
    env/bin/python tools/headline_comparison.py
    env/bin/python tools/headline_comparison.py --seeds 0,1,2,3,4 --n-ticks 300
    env/bin/python tools/headline_comparison.py --output-dir .claude/tmp/headline
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(_HERE))

from simulator.architectures import ARCHITECTURES  # noqa: E402
from simulator.metrics import compute_metrics       # noqa: E402
from simulator.runner import simulate_one           # noqa: E402
from simulator.workloads import WORKLOADS           # noqa: E402


# ---------------------------------------------------------------------------
# Fixed configuration — these define the "fair" comparison.
# ---------------------------------------------------------------------------

ARCHS = [
    ("PPO solo",       "A1_ppo_argmax"),
    ("PPO+PI (real)",  "A3_ppopi_aw"),
    ("GPPPO (ours)",   "A4_gpppo_final"),
]

SCENARIOS = [
    # (label, workload, noise_dist, noise_std, has_drift)
    ("Step drift λ=22→80, gauss",        "step",          "gaussian",       0.10, True),
    ("Stationary λ=22, ρ-amp",           "stationary22",  "rho_amplified",  0.10, False),
    ("Step drift λ=22→80, ρ-amp",        "step",          "rho_amplified",  0.10, True),
]


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seeds", default="0,1,2,3,4")
    p.add_argument("--n-ticks", type=int, default=300)
    p.add_argument("--sla", type=float, default=0.25)
    p.add_argument("--service-rate", type=float, default=10.0)
    p.add_argument("--init-cores", type=float, default=1.0)
    p.add_argument("--min-cores", type=float, default=1.0,
                   help="floor on cores (default 1 — tuned-PI default)")
    p.add_argument("--max-cores", type=float, default=28.0)
    p.add_argument("--st", type=float, default=1.0)
    p.add_argument("--lam-pre", type=float, default=22.0)
    p.add_argument("--lam-post", type=float, default=80.0)
    p.add_argument("--drift-at", type=int, default=100)
    p.add_argument("--output-dir", default=".claude/tmp/headline")
    p.add_argument("--plant-model", type=str, default="fluid",
                   choices=("fluid", "mmc"),
                   help="'fluid' (M/M/1-effective + multiplicative noise) or "
                        "'mmc' (discrete-event M/M/c with Poisson arrivals)")
    p.add_argument("--bc", type=float, default=None,
                   help="PI integral gain (override factory default 5.0). "
                        "Use values from `tune_pi.py`.")
    p.add_argument("--dc", type=float, default=None,
                   help="PI proportional gain (override factory default 10.0).")
    p.add_argument("--error-form", default="inverse",
                   choices=("inverse", "linear", "log"),
                   help="PI error formulation (default inverse for backward compat; "
                        "use 'linear' or 'log' for the tuned PI from tune_pi.py)")
    p.add_argument("--rt-deadband-frac", type=float, default=0.0,
                   help="PI deadband on |rt-sp|/sp (default 0 = off; use 0.30 for tuned PI)")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def _bind_workload(name: str, args):
    raw = WORKLOADS[name]
    if name == "step":
        return lambda t, _f=raw: _f(t, lam_pre=args.lam_pre,
                                    lam_post=args.lam_post,
                                    drift_at=args.drift_at)
    return raw


def run_grid(args) -> dict:
    """Run (arch × scenario × seed) and aggregate."""
    seeds = [int(s) for s in args.seeds.split(",")]
    out_dir = Path(args.output_dir) / time.strftime("hl-%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    total = len(ARCHS) * len(SCENARIOS) * len(seeds)
    done = 0
    t_start = time.time()

    for sc_label, wl_name, noise_dist, noise_std, has_drift in SCENARIOS:
        wl_fn = _bind_workload(wl_name, args)
        drift_t = args.drift_at if has_drift else None
        for arch_label, arch_key in ARCHS:
            _, factory = ARCHITECTURES[arch_key]
            for seed in seeds:
                done += 1
                t_run = time.time()
                if args.verbose:
                    print(f"  [{done:2d}/{total}] {arch_key:18s} | {sc_label:35s} | seed={seed}",
                          end="", flush=True)
                log_path = out_dir / f"{arch_key}_{wl_name}_{noise_dist}_seed{seed}.log"
                extra = {}
                if args.bc is not None: extra["BC"] = args.bc
                if args.dc is not None: extra["DC"] = args.dc
                if args.error_form != "inverse": extra["error_form"] = args.error_form
                if args.rt_deadband_frac > 0: extra["rt_deadband_frac"] = args.rt_deadband_frac
                history = simulate_one(
                    factory, wl_fn,
                    n_ticks=args.n_ticks, sla=args.sla,
                    service_rate=args.service_rate,
                    noise_std=noise_std, noise_dist=noise_dist,
                    init_cores=args.init_cores, min_cores=args.min_cores,
                    max_cores=args.max_cores, st=args.st, period=1,
                    train=False, seed=seed, log_path=log_path,
                    plant_model=args.plant_model,
                    extra_common=extra if extra else None,
                )
                m = compute_metrics(history, sla=args.sla, drift_at=drift_t)
                m.update({"arch_key": arch_key, "arch_label": arch_label,
                          "scenario": sc_label, "seed": seed})
                results.append(m)
                if args.verbose:
                    print(f"   {time.time() - t_run:4.1f}s   "
                          f"cost={m['cost']:.0f}  viol={m['sla_violation_rate']:.1%}",
                          flush=True)

    summary = {}
    for sc_label, *_ in SCENARIOS:
        for arch_label, arch_key in ARCHS:
            runs = [r for r in results
                    if r["scenario"] == sc_label and r["arch_key"] == arch_key]
            if not runs:
                continue
            agg = {
                "cost":               float(np.median([r["cost"] for r in runs])),
                "sla_violation_rate": float(np.median([r["sla_violation_rate"] for r in runs])),
                "p95_rt":             float(np.median([r["p95_rt"] for r in runs])),
                "p99_rt":             float(np.median([r["p99_rt"] for r in runs])),
                "tail_exceedance":    float(np.median([r["tail_exceedance"] for r in runs])),
                "avg_cores":          float(np.median([r["avg_cores"] for r in runs])),
                "n_seeds":            len(runs),
            }
            summary[(sc_label, arch_label)] = agg

    runtime = time.time() - t_start

    # Persist artefacts
    with open(out_dir / "raw_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    with open(out_dir / "summary.json", "w") as f:
        json.dump({f"{k[0]} || {k[1]}": v for k, v in summary.items()},
                  f, indent=2)

    return {"summary": summary, "out_dir": out_dir, "runtime": runtime,
            "n_seeds": len(seeds)}


def render_table(summary: dict, *, n_seeds: int, sla: float) -> str:
    """Render the headline 3×3 comparison table."""
    arch_labels = [a[0] for a in ARCHS]
    sc_labels = [s[0] for s in SCENARIOS]

    # Compute deltas of GPPPO vs each baseline
    def get(scenario, arch, field):
        return summary[(scenario, arch)][field]

    def delta_pct(scenario, our, baseline, field, *, lower_better=True):
        a = get(scenario, our, field)
        b = get(scenario, baseline, field)
        if b == 0:
            return float("nan")
        d = (a - b) / abs(b) * 100.0
        return d  # positive = ours is higher; user can interpret with lower_better

    def sign(value, *, lower_better=True):
        if np.isnan(value):
            return "n/a"
        return f"{value:+.0f}%"

    plant_model = getattr(render_table, "_plant_model", "fluid")
    lines: list[str] = []
    lines.append("=" * 96)
    lines.append(f"  HEADLINE COMPARISON   n_seeds={n_seeds}   SLA={sla:.2f}s   "
                 f"plant={plant_model}   medians across seeds (frozen pre-trained PPO)")
    lines.append("=" * 96)
    lines.append("")

    # Header rows
    sep = "  "
    col_w = 26
    metric_w = 16
    arch_w = 16

    # Scenario row
    lines.append(" " * arch_w + sep + sep.join(s[:col_w-1].ljust(col_w) for s in sc_labels))
    metric_header = "cost  viol%  p99    tail".ljust(col_w)
    lines.append("Architecture".ljust(arch_w) + sep + sep.join(metric_header for _ in sc_labels))
    lines.append("-" * (arch_w + (col_w + len(sep)) * len(sc_labels)))

    # Data rows
    for arch in arch_labels:
        cells = []
        for sc in sc_labels:
            r = summary[(sc, arch)]
            cell = (f"{r['cost']:5.0f}  {100*r['sla_violation_rate']:4.1f}%  "
                    f"{r['p99_rt']:4.2f}  {r['tail_exceedance']:5.1f}").ljust(col_w)
            cells.append(cell)
        lines.append(arch.ljust(arch_w) + sep + sep.join(cells))

    lines.append("-" * (arch_w + (col_w + len(sep)) * len(sc_labels)))

    # Delta vs PPO solo
    our = "GPPPO (ours)"
    base_solo = "PPO solo"
    base_pi   = "PPO+PI (real)"

    def delta_row(label, baseline_label, field, fmt="{:+.0f}%"):
        cells = []
        for sc in sc_labels:
            a = summary[(sc, our)][field]
            b = summary[(sc, baseline_label)][field]
            if b == 0:
                cell = "n/a".ljust(col_w)
            else:
                d = (a - b) / abs(b) * 100.0
                cell = fmt.format(d).ljust(col_w)
            cells.append(cell)
        lines.append(label.ljust(arch_w) + sep + sep.join(cells))

    def ratio_row(label, baseline_label, field):
        """Show ours/baseline ratio (e.g., 2× more or fewer)."""
        cells = []
        for sc in sc_labels:
            a = summary[(sc, our)][field]
            b = summary[(sc, baseline_label)][field]
            if b == 0:
                cell = "n/a"
            elif a == 0:
                cell = "0 (perfect)"
            else:
                ratio = b / a
                cell = f"{ratio:.1f}× ↓ (ours)" if ratio > 1 else f"{1/ratio:.1f}× ↑ (ours)"
            cells.append(cell.ljust(col_w))
        lines.append(label.ljust(arch_w) + sep + sep.join(cells))

    lines.append("Δ ours vs PPO solo:")
    delta_row("  cost",      base_solo, "cost")
    delta_row("  viol%",     base_solo, "sla_violation_rate")
    delta_row("  tail-AUC",  base_solo, "tail_exceedance")
    ratio_row("  viol ratio", base_solo, "sla_violation_rate")

    lines.append("-" * (arch_w + (col_w + len(sep)) * len(sc_labels)))
    lines.append("Δ ours vs PPO+PI:")
    delta_row("  cost",      base_pi, "cost")
    delta_row("  viol%",     base_pi, "sla_violation_rate")
    delta_row("  tail-AUC",  base_pi, "tail_exceedance")
    ratio_row("  viol ratio", base_pi, "sla_violation_rate")

    lines.append("=" * 96)
    lines.append("")
    lines.append("Notes:")
    lines.append("  - PPO solo: frozen pre-trained PPO with argmax action selection.")
    lines.append("  - PPO+PI (real): properly-tuned PPO+PI with anti-windup back-calculation")
    lines.append("    and error-clip (CT-R2). NOT the windup-bug version.")
    lines.append("  - GPPPO (ours): same anti-windup PI subsystem + single architectural fix")
    lines.append("    (GP-R2: GP regresses on observed SLA shortfall, not on PI compensation).")
    lines.append("  - Plant: M/M/1 with effective μ=10 req/s/core. SLA=0.25s. drift_at=100.")
    lines.append("  - tail-AUC: ∫ max(0, RT − SLA) dt over the run.")
    lines.append("  - 'ρ-amp' noise: σ_eff = σ·(1 + 4·max(0, ρ−0.5)) — state-dep utilization.")
    return "\n".join(lines)


def main():
    args = parse_args()
    print(f"Running headline comparison: {len(ARCHS)} archs × {len(SCENARIOS)} "
          f"scenarios × {len(args.seeds.split(','))} seeds = "
          f"{len(ARCHS) * len(SCENARIOS) * len(args.seeds.split(','))} simulations")
    print()

    grid = run_grid(args)
    render_table._plant_model = args.plant_model  # passed via attribute (lazy)
    table = render_table(grid["summary"], n_seeds=grid["n_seeds"], sla=args.sla)
    print(table)
    print(f"\nTotal runtime: {grid['runtime']:.1f}s")
    print(f"Artefacts: {grid['out_dir']}/")
    with open(grid["out_dir"] / "headline_table.txt", "w") as f:
        f.write(table)


if __name__ == "__main__":
    main()
