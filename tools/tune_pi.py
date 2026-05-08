#!/usr/bin/env python
"""Two-stage PI tuning for stable autoscaling controller behavior.

PHASE 1 — Stability search (stationary regime, no drift)
    Grid-search (BC, DC) gains; rank by cores standard deviation (oscillation).
    Filter: viol_rate ≤ --max-viol-rate (don't accept "stable but always violating").

PHASE 2 — Drift validation (step regime)
    Re-run best (BC*, DC*) on step drift; verify recovery_time ≤ --max-recovery-ticks.

The tuning is independent of the plant model — switch via --plant-model.
Tuned gains are reported on stdout; persist to JSON in --output-dir.

Pass the tuned (BC*, DC*) to other scripts:
    env/bin/python tools/headline_comparison.py --bc <BC*> --dc <DC*>
    env/bin/python tools/simulate_architectures.py --bc <BC*> --dc <DC*>

Examples
--------
    # Default tuning on M/M/c, stationary λ=22, drift validation 22→80
    env/bin/python tools/tune_pi.py

    # Tune on the fluid plant for comparison
    env/bin/python tools/tune_pi.py --plant-model fluid

    # Custom grid + relaxed viol threshold
    env/bin/python tools/tune_pi.py --bc-grid 0.05,0.1,0.2,0.5 \\
        --dc-grid 0.5,1.0,2.0 --max-viol-rate 0.15

    # Tune for a different load scale
    env/bin/python tools/tune_pi.py --lambda-stationary 40 \\
        --lambda-drift-pre 40 --lambda-drift-post 100
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from itertools import product
from pathlib import Path

import numpy as np

_HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(_HERE))

from simulator.architectures import make_a3_ppopi_aw  # noqa: E402
from simulator.metrics import compute_metrics          # noqa: E402
from simulator.runner import simulate_one              # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Plant
    p.add_argument("--plant-model", default="mmc", choices=("fluid", "mmc"),
                   help="fluid (M/M/1-effective + multiplicative noise) or "
                        "mmc (discrete-event M/M/c with Poisson arrivals)")
    # Grid
    p.add_argument("--bc-grid", default="0.05,0.1,0.2,0.3,0.5,0.75,1.0,1.5,2.0,3.0",
                   help="comma list of BC values to test (default: 10-pt fine grid)")
    p.add_argument("--dc-grid", default="0.1,0.2,0.3,0.5,0.75,1.0,1.5,2.0,3.0,5.0",
                   help="comma list of DC values to test (default: 10-pt fine grid)")
    # Phase 1 scenario
    p.add_argument("--lambda-stationary", type=float, default=22.0,
                   help="constant λ for Phase 1 stability test (default: 22 = TweetGen mean)")
    # Phase 2 scenario
    p.add_argument("--lambda-drift-pre", type=float, default=22.0)
    p.add_argument("--lambda-drift-post", type=float, default=80.0)
    p.add_argument("--drift-at", type=int, default=100)
    # Acceptance criteria
    p.add_argument("--max-viol-rate", type=float, default=0.30,
                   help="reject (BC,DC) with median viol_rate above this (default: 30%%, "
                        "loose — PI is honest mean tracker, GP later reduces tail viol)")
    p.add_argument("--max-recovery-ticks", type=int, default=20,
                   help="reject if drift recovery slower than this (default: 20 ticks)")
    p.add_argument("--criterion", default="track_mean",
                   choices=("track_mean", "min_std", "min_cost"),
                   help="selection: track_mean (min std subject to mean ≈ optimal c), "
                        "min_std (raw lowest std), min_cost (lowest cost feasible)")
    p.add_argument("--target-mean-cores", type=float, default=None,
                   help="target cores_mean for 'track_mean' criterion. "
                        "Default: ceil(λ/μ)+0.5 (slightly above the saturation boundary)")
    p.add_argument("--target-mean-tol", type=float, default=1.5,
                   help="±tolerance around --target-mean-cores")
    # Generic plant + run
    p.add_argument("--seeds", default="0,1,2")
    p.add_argument("--n-ticks", type=int, default=300)
    p.add_argument("--sla", type=float, default=0.25)
    p.add_argument("--service-rate", type=float, default=10.0)
    p.add_argument("--init-cores", type=float, default=1.0)
    p.add_argument("--min-cores", type=float, default=2.0,
                   help="floor on cores. Default 2.0 (avoids actuator collapse to 0.5).")
    p.add_argument("--max-cores", type=float, default=28.0)
    p.add_argument("--st", type=float, default=0.8,
                   help="setpoint = SLA·st. Default 0.8 (sp=0.20 < SLA=0.25, "
                        "places setpoint below RT(c=3) so equilibrium is integer-aligned).")
    p.add_argument("--rt-deadband-frac", type=float, default=0.30,
                   help="hold cores when |rt - sp| < frac·sp. Default 0.30 (CT-expert recommendation)")
    p.add_argument("--anti-windup", action="store_true", default=True,
                   help="enable Astrom-Hagglund back-calculation (default ON)")
    p.add_argument("--no-anti-windup", action="store_false", dest="anti_windup")
    p.add_argument("--e-clip", type=float, default=10.0,
                   help="symmetric clip on error magnitude (None to disable)")
    p.add_argument("--noise-dist", default="gaussian",
                   choices=("gaussian", "lognormal", "pareto", "rho_amplified"))
    p.add_argument("--noise-std", type=float, default=0.10)
    p.add_argument("--error-form", default="inverse",
                   choices=("inverse", "linear", "log"),
                   help="PI error formulation. 'inverse' = legacy 1/sp − 1/rt "
                        "(asymmetric, root cause of sawtooth). 'linear' = "
                        "(rt − sp)/sp. 'log' = log(rt) − log(sp) (Hellerstein 2004).")
    # IO
    p.add_argument("--output-dir", default=".claude/tmp/tune_pi")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


# ---------------------------------------------------------------------------
def _run_one(args, bc, dc, seed, workload_fn, drift_at=None):
    """One simulate_one call with given (BC, DC). Returns metrics."""
    history = simulate_one(
        make_a3_ppopi_aw, workload_fn,
        n_ticks=args.n_ticks, sla=args.sla,
        service_rate=args.service_rate,
        noise_std=args.noise_std, noise_dist=args.noise_dist,
        init_cores=args.init_cores, min_cores=args.min_cores,
        max_cores=args.max_cores, st=args.st,
        period=1, train=False, seed=seed,
        extra_common={"BC": float(bc), "DC": float(dc),
                      "error_form": args.error_form,
                      "rt_deadband_frac": args.rt_deadband_frac,
                      "anti_windup": args.anti_windup,
                      "e_clip": args.e_clip},
        plant_model=args.plant_model,
    )
    cores = np.array([h["cores"] for h in history])
    m = compute_metrics(history, sla=args.sla, drift_at=drift_at)
    return {
        "cores_std": float(cores.std()),
        "cores_mean": float(cores.mean()),
        "cores_min": float(cores.min()),
        "cores_max": float(cores.max()),
        "viol_rate": m["sla_violation_rate"],
        "cost": m["cost"],
        "p99_rt": m["p99_rt"],
        "tail_exceedance": m["tail_exceedance"],
        "time_to_recovery": m.get("time_to_recovery"),
    }


# ---------------------------------------------------------------------------
def run_phase1(args):
    """Grid search on stationary scenario. Returns ranked table + best."""
    bc_grid = [float(x) for x in args.bc_grid.split(",")]
    dc_grid = [float(x) for x in args.dc_grid.split(",")]
    seeds = [int(s) for s in args.seeds.split(",")]
    n_combos = len(bc_grid) * len(dc_grid)

    print(f"PHASE 1 — Stability search   plant={args.plant_model}   "
          f"λ_stationary={args.lambda_stationary}   "
          f"grid={n_combos} combos × {len(seeds)} seeds = "
          f"{n_combos*len(seeds)} simulations")
    print()

    workload = lambda t: float(args.lambda_stationary)

    grid_results: dict[tuple[float, float], list[dict]] = {}
    total = n_combos * len(seeds)
    done = 0
    t0 = time.time()
    for bc, dc in product(bc_grid, dc_grid):
        rs = []
        for seed in seeds:
            done += 1
            if args.verbose:
                print(f"  [{done:3d}/{total}] BC={bc:5.2f} DC={dc:5.2f} seed={seed} ...",
                      end="\r", flush=True)
            rs.append(_run_one(args, bc, dc, seed, workload))
        grid_results[(bc, dc)] = rs

    if args.verbose:
        print()
    print(f"  Phase 1 done in {time.time()-t0:.1f}s")
    print()

    # Aggregate (median across seeds)
    table = []
    for (bc, dc), rs in grid_results.items():
        table.append({
            "BC": bc, "DC": dc,
            "std":  float(np.median([r["cores_std"] for r in rs])),
            "mean": float(np.median([r["cores_mean"] for r in rs])),
            "viol": float(np.median([r["viol_rate"] for r in rs])),
            "cost": float(np.median([r["cost"] for r in rs])),
            "p99":  float(np.median([r["p99_rt"] for r in rs])),
        })
    table.sort(key=lambda r: r["std"])

    # Print full grid sorted by stability
    print(f"  {'BC':>6} {'DC':>6}   {'std':>6} {'mean':>6}  {'viol%':>6}  "
          f"{'cost':>6}  {'p99':>6}   feasible")
    print("  " + "-" * 70)
    for r in table:
        ok = "✓" if r["viol"] <= args.max_viol_rate else "✗"
        print(f"  {r['BC']:6.2f} {r['DC']:6.2f}   "
              f"{r['std']:6.2f} {r['mean']:6.2f}  "
              f"{100*r['viol']:5.1f}%  {r['cost']:6.0f}  "
              f"{r['p99']:6.3f}   {ok}")

    feasible = [r for r in table if r["viol"] <= args.max_viol_rate]
    if not feasible:
        print(f"\n  ⚠️  No (BC, DC) satisfies viol ≤ {100*args.max_viol_rate:.0f}%.")
        print(f"     Try: relax --max-viol-rate, or expand --bc-grid / --dc-grid.")
        return table, None

    # Apply selection criterion
    if args.criterion == "track_mean":
        target = args.target_mean_cores
        if target is None:
            # default: ceil(λ/μ) + 0.5 (slightly above saturation boundary)
            target = math.ceil(args.lambda_stationary / args.service_rate) + 0.5
        tol = args.target_mean_tol
        in_target = [r for r in feasible
                     if abs(r["mean"] - target) <= tol]
        if not in_target:
            print(f"\n  ⚠️  No combo with cores_mean ∈ [{target-tol:.1f}, {target+tol:.1f}].")
            print(f"     Falling back to feasible set for selection.")
            in_target = feasible
        in_target.sort(key=lambda r: r["std"])
        best = in_target[0]
        crit_label = (f"min std with viol≤{100*args.max_viol_rate:.0f}% AND "
                      f"mean ∈ [{target-tol:.1f}, {target+tol:.1f}] (track-mean)")
    elif args.criterion == "min_cost":
        feasible.sort(key=lambda r: r["cost"])
        best = feasible[0]
        crit_label = f"min cost with viol≤{100*args.max_viol_rate:.0f}%"
    else:  # min_std
        best = feasible[0]
        crit_label = f"min std with viol≤{100*args.max_viol_rate:.0f}%"

    print(f"\n  → BEST ({crit_label}):")
    print(f"      BC = {best['BC']}    DC = {best['DC']}")
    print(f"      cores_std = {best['std']:.2f}    cores_mean = {best['mean']:.2f}    "
          f"viol = {100*best['viol']:.1f}%    cost = {best['cost']:.0f}    p99 = {best['p99']:.3f}s")
    return table, best


# ---------------------------------------------------------------------------
def run_phase2(args, best):
    """Validate best (BC*, DC*) on step drift scenario."""
    print(f"\nPHASE 2 — Drift validation   "
          f"λ {args.lambda_drift_pre}→{args.lambda_drift_post}   "
          f"drift_at={args.drift_at}   recovery threshold ≤ {args.max_recovery_ticks} ticks")
    print()

    seeds = [int(s) for s in args.seeds.split(",")]
    pre, post, drift_at = args.lambda_drift_pre, args.lambda_drift_post, args.drift_at
    workload = lambda t: float(post if t >= drift_at else pre)

    rs = [_run_one(args, best["BC"], best["DC"], s, workload, drift_at=drift_at)
          for s in seeds]

    rec_med = float(np.median([
        r["time_to_recovery"] if r["time_to_recovery"] is not None else 9999
        for r in rs
    ]))
    viol_med = float(np.median([r["viol_rate"] for r in rs]))
    cost_med = float(np.median([r["cost"] for r in rs]))
    std_med = float(np.median([r["cores_std"] for r in rs]))

    print(f"  recovery: {rec_med:.0f} ticks   (threshold: ≤ {args.max_recovery_ticks})")
    print(f"  viol:     {100*viol_med:.1f}%")
    print(f"  cost:     {cost_med:.0f}")
    print(f"  cores_std: {std_med:.2f}")

    validated = rec_med <= args.max_recovery_ticks
    if validated:
        print(f"\n  ✅ VALIDATED on drift recovery.")
    else:
        print(f"\n  ⚠️  Recovery too slow ({rec_med:.0f} > {args.max_recovery_ticks}).")
        print(f"     The PI is stable but sluggish on drift. Consider:")
        print(f"     - relax --max-viol-rate (allow more aggressive gains)")
        print(f"     - relax --max-recovery-ticks (accept slower drift response)")
        print(f"     - expand --bc-grid / --dc-grid")

    return validated, {"recovery": rec_med, "viol": viol_med, "cost": cost_med, "std": std_med}


# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    out_dir = Path(args.output_dir) / time.strftime("tune-%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    table, best = run_phase1(args)
    if best is None:
        with open(out_dir / "tuning_result.json", "w") as f:
            json.dump({"args": vars(args), "phase1_table": table, "best": None}, f, indent=2)
        sys.exit(1)

    validated, validation = run_phase2(args, best)

    print()
    print("=" * 64)
    print(f"  RECOMMENDED PI GAINS:   BC = {best['BC']}    DC = {best['DC']}")
    if validated:
        print(f"  Validated: stable in stationary AND recovers from drift in {validation['recovery']:.0f} ticks.")
    else:
        print(f"  NOT validated on drift — proceed with caution.")
    print("=" * 64)
    print()
    print("Use these gains in other simulator scripts:")
    print(f"  env/bin/python tools/headline_comparison.py "
          f"--plant-model {args.plant_model} --bc {best['BC']} --dc {best['DC']}")
    print(f"  env/bin/python tools/simulate_architectures.py "
          f"--plant-model {args.plant_model} --bc {best['BC']} --dc {best['DC']} "
          f"--workloads stationary22,step --seeds 0,1,2,3,4")
    print()

    # Persist
    with open(out_dir / "tuning_result.json", "w") as f:
        json.dump({
            "args": vars(args),
            "phase1_table": table,
            "best": best,
            "phase2_validation": validation,
            "validated": validated,
        }, f, indent=2)
    print(f"Artefacts: {out_dir}/")


if __name__ == "__main__":
    main()
