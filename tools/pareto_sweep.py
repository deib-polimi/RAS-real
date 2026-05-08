#!/usr/bin/env python
"""GPPPO Pareto-curve sweep on two knobs (β posterior percentile, H lookahead horizon).

Sweeps a (β × H) grid of GPPPO configurations on a single workload+plant, plus
the two baselines (PPO solo, PPO+PI tuned). Produces:

  1. Console + summary.txt with Pareto-ranked table.
  2. pareto.png — scatter cost vs viol%, baselines marked, Pareto frontier highlighted.
  3. trajectory_canonical.png — for one canonical run, λ(t) + RT(t) + cores(t)
     with drift onset and OOD region annotated.
  4. summary.json + per-config CSV.

Plant-agnostic via --plant-model {fluid,mmc}. Re-runnable in 10-30s.

Examples
--------
    # Default: M/M/c, step drift λ=22→80 at t=100, 5×4 grid, n=5 seeds
    env/bin/python tools/pareto_sweep.py

    # Re-run on fluid plant for cross-validation
    env/bin/python tools/pareto_sweep.py --plant-model fluid

    # Coarser grid for quick smoke test
    env/bin/python tools/pareto_sweep.py --beta-grid 50,95,99 --h-grid 1,5

    # Different drift scenario
    env/bin/python tools/pareto_sweep.py --lam-pre 30 --lam-post 60 --drift-at 150
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from itertools import product
from pathlib import Path

import numpy as np

_HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(_HERE))

from simulator.architectures import (   # noqa: E402
    make_a1_ppo_argmax, make_a3_ppopi_aw, _make_a4,
)
from simulator.metrics import compute_metrics, windowed_metrics  # noqa: E402
from simulator.runner import simulate_one      # noqa: E402
from simulator.workloads import WORKLOADS      # noqa: E402
from simulator import service_drifts           # noqa: E402


# Training-distribution range (from TweetGen: bias=40, shift=10 → λ ∈ [10, 50])
TRAIN_LAM_MIN, TRAIN_LAM_MAX = 10.0, 50.0


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Sweep grid
    p.add_argument("--beta-grid", default="50,75,90,95,99",
                   help="GP posterior percentile grid (lower=mean-bias, higher=safety-bias)")
    p.add_argument("--h-grid", default="1,3,5,10",
                   help="GP prediction horizon (lookahead ticks; 1 = current behavior)")
    # Plant + workload
    p.add_argument("--plant-model", default="mmc", choices=("fluid", "mmc"))
    p.add_argument("--workload", default="step",
                   choices=("step", "stationary22", "linear_ramp", "recurring_step"))
    p.add_argument("--recurring-drifts", default="300,600,900",
                   help="comma list of drift tick points (recurring_step only)")
    p.add_argument("--lam-pre", type=float, default=22.0)
    p.add_argument("--lam-post", type=float, default=80.0)
    p.add_argument("--drift-at", type=int, default=100)
    p.add_argument("--noise-dist", default="gaussian",
                   choices=("gaussian", "lognormal", "pareto", "rho_amplified"))
    p.add_argument("--noise-std", type=float, default=0.10)
    # μ drift (UNOBSERVED capacity degradation)
    p.add_argument("--service-drift", default="none",
                   choices=("none", "step", "ramp", "bursty"),
                   help="Apply drift to service rate μ (UNOBSERVED by PPO state). "
                        "step: μ halves at --service-drift-at. "
                        "ramp: μ degrades linearly over --service-drift-window. "
                        "bursty: μ alternates 1.0/factor every --service-drift-period/2 ticks.")
    p.add_argument("--service-drift-factor", type=float, default=0.5,
                   help="μ multiplier under degradation (e.g. 0.5 = halves)")
    p.add_argument("--service-drift-at", type=float, default=300.0)
    p.add_argument("--service-drift-window", default="300,900",
                   help="ramp drift window (start,end)")
    p.add_argument("--service-drift-period", type=float, default=200.0,
                   help="bursty drift period (full cycle = 2 half-periods)")
    # Common controller config (tuned defaults from tune_pi.py)
    p.add_argument("--bc", type=float, default=0.3)
    p.add_argument("--dc", type=float, default=0.1)
    # Knob #3: adaptive retraining frequency
    p.add_argument("--gp-adaptive-train", action="store_true",
                   help="Trigger GP retraining when drift detected via buffer-target "
                        "z-score window comparison (knob #3, beyond β and H).")
    p.add_argument("--gp-drift-threshold", type=float, default=1.5,
                   help="z-score threshold for adaptive retraining (default 1.5σ)")
    p.add_argument("--gp-min-train-interval", type=int, default=10,
                   help="min ticks between adaptive retrainings (default 10)")
    p.add_argument("--gp-eviction-keep", type=int, default=0,
                   help="when adaptive trigger fires, evict buffer to last K samples "
                        "(default 0 = disabled). Useful values: 35-50 for fresh-data retrain.")
    p.add_argument("--error-form", default="linear",
                   choices=("inverse", "linear", "log"))
    p.add_argument("--rt-deadband-frac", type=float, default=0.30)
    p.add_argument("--st", type=float, default=0.8)
    p.add_argument("--init-cores", type=float, default=1.0)
    p.add_argument("--min-cores", type=float, default=1.0)
    p.add_argument("--max-cores", type=float, default=28.0)
    p.add_argument("--service-rate", type=float, default=10.0)
    p.add_argument("--sla", type=float, default=0.25)
    # Run
    p.add_argument("--seeds", default="0,1,2,3,4")
    p.add_argument("--n-ticks", type=int, default=300)
    p.add_argument("--transient-window", type=int, default=100,
                   help="ticks AFTER drift_event_end considered as transient. "
                        "Steady-state window starts after this. Default 100.")
    p.add_argument("--canonical-beta", type=int, default=95,
                   help="β for the trajectory plot")
    p.add_argument("--canonical-h", type=int, default=5,
                   help="H for the trajectory plot")
    p.add_argument("--output-dir", default=".claude/tmp/pareto_sweep")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


# ---------------------------------------------------------------------------
def _compute_windows(args):
    """Return named windows {pre, transient, steady} based on the drift configuration.

    For step drifts: drift event = single point. Transient = [drift, drift+window).
    For ramp drifts: drift event = ramp interval. Transient = [ramp_start, ramp_end+window).
    """
    n = args.n_ticks
    if args.service_drift == "step":
        de = int(args.service_drift_at)
        steady_start = de + args.transient_window
        return {"pre": (0, de),
                "transient": (de, steady_start),
                "steady": (steady_start, n)}
    if args.service_drift == "ramp":
        s, e = (int(float(x)) for x in args.service_drift_window.split(","))
        steady_start = e + args.transient_window
        return {"pre": (0, s),
                "transient": (s, steady_start),
                "steady": (steady_start, n)}
    if args.workload == "step":
        de = args.drift_at
        steady_start = de + args.transient_window
        return {"pre": (0, de),
                "transient": (de, steady_start),
                "steady": (steady_start, n)}
    # Default: just pre vs steady (no clear drift)
    return {"pre": (0, n // 2), "steady": (n // 2, n)}


def _bind_service_drift(args):
    """Build service-drift fn closure from CLI args."""
    if args.service_drift == "none":
        return None
    if args.service_drift == "step":
        return lambda t: service_drifts.step(t, factor=args.service_drift_factor,
                                              drift_at=args.service_drift_at)
    if args.service_drift == "ramp":
        s, e = (float(x) for x in args.service_drift_window.split(","))
        return lambda t: service_drifts.ramp(t, factor_end=args.service_drift_factor,
                                              ramp_start=s, ramp_end=e)
    if args.service_drift == "bursty":
        return lambda t: service_drifts.bursty(t, factor_low=args.service_drift_factor,
                                                period=args.service_drift_period)
    return None


def _bind_workload(name, args):
    raw = WORKLOADS[name]
    if name == "step":
        return lambda t, _f=raw: _f(t, lam_pre=args.lam_pre, lam_post=args.lam_post,
                                    drift_at=args.drift_at)
    if name == "recurring_step":
        drifts = tuple(int(x) for x in args.recurring_drifts.split(","))
        return lambda t, _f=raw: _f(t, lam_low=args.lam_pre,
                                    lam_high=args.lam_post,
                                    drift_points=drifts)
    return raw


def _common_config(args):
    return {
        "BC": args.bc, "DC": args.dc,
        "error_form": args.error_form,
        "rt_deadband_frac": args.rt_deadband_frac,
        "anti_windup": True, "e_clip": 10.0,
        "gp_adaptive_train": getattr(args, "gp_adaptive_train", False),
        "gp_drift_threshold": getattr(args, "gp_drift_threshold", 1.5),
        "gp_min_train_interval": getattr(args, "gp_min_train_interval", 10),
        "gp_eviction_keep": getattr(args, "gp_eviction_keep", 0),
    }


def _factory_for_gpppo(beta, H):
    """Build a GPPPO factory closure with given (beta, H)."""
    def fac(common):
        common2 = dict(common)
        common2["gp_percentile"] = beta
        common2["gp_lookahead_horizon"] = H
        ctrl = _make_a4(common2,
                        gp_target_mode="sla_shortfall",
                        pi_anti_windup=True)
        ctrl.deterministic_eval = True   # match A1_ppo_argmax for fairness
        return ctrl
    return fac


def _run_config(args, factory, label, seeds, workload_fn, drift_at, out_dir,
                save_traces=False, service_drift_fn=None, windows=None):
    """Run one configuration across seeds; return list of metric dicts + (optional) histories."""
    common_extra = _common_config(args)
    metrics_list = []
    histories = {}
    for seed in seeds:
        history = simulate_one(
            factory, workload_fn,
            n_ticks=args.n_ticks, sla=args.sla,
            service_rate=args.service_rate,
            noise_std=args.noise_std, noise_dist=args.noise_dist,
            init_cores=args.init_cores, min_cores=args.min_cores,
            max_cores=args.max_cores, st=args.st,
            period=1, train=False, seed=seed,
            extra_common=common_extra,
            plant_model=args.plant_model,
            service_drift_fn=service_drift_fn,
        )
        cores = np.array([h["cores"] for h in history])
        m = compute_metrics(history, sla=args.sla, drift_at=drift_at)
        m.update({"label": label, "seed": seed,
                  "cores_std": float(cores.std()),
                  "cores_mean": float(cores.mean())})
        if windows is not None:
            m["windowed"] = windowed_metrics(history, sla=args.sla, windows=windows)
        metrics_list.append(m)
        if save_traces:
            histories[seed] = history
    return metrics_list, histories


# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    seeds = [int(s) for s in args.seeds.split(",")]
    betas = [int(b) for b in args.beta_grid.split(",")]
    Hs    = [int(h) for h in args.h_grid.split(",")]

    out_dir = Path(args.output_dir) / time.strftime("sweep-%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    workload_fn = _bind_workload(args.workload, args)
    service_drift_fn = _bind_service_drift(args)
    windows = _compute_windows(args)
    if args.workload == "step":
        drift_at = args.drift_at
    elif args.workload == "recurring_step":
        # use first drift for time_to_recovery measurement
        drift_at = int(args.recurring_drifts.split(",")[0])
    else:
        drift_at = None

    print(f"\nPARETO SWEEP   plant={args.plant_model}   workload={args.workload}   "
          f"service_drift={args.service_drift}   n_seeds={len(seeds)}")
    print(f"  β grid: {betas}")
    print(f"  H grid: {Hs}")
    print(f"  Total: {len(betas)*len(Hs)} GPPPO configs + 2 baselines = "
          f"{(len(betas)*len(Hs)+2) * len(seeds)} simulations")
    print(f"  PI: BC={args.bc} DC={args.dc} error_form={args.error_form} "
          f"deadband={args.rt_deadband_frac}  st={args.st}  min_cores={args.min_cores}")
    print(f"  Output dir: {out_dir}")
    print()

    t0 = time.time()
    all_results: list[dict] = []
    canonical_history = None

    # ---- Baselines ----
    print("Running baselines...")
    for label, factory in [("PPO solo", make_a1_ppo_argmax),
                           ("PPO+PI (tuned)", make_a3_ppopi_aw)]:
        metrics, _ = _run_config(args, factory, label, seeds, workload_fn,
                                 drift_at, out_dir, service_drift_fn=service_drift_fn,
                                 windows=windows)
        all_results.extend(metrics)
        med = {
            "cost": np.median([m["cost"] for m in metrics]),
            "viol": np.median([m["sla_violation_rate"] for m in metrics]),
            "p99":  np.median([m["p99_rt"] for m in metrics]),
        }
        print(f"  {label:18s} → cost={med['cost']:6.0f}  viol={100*med['viol']:5.1f}%  "
              f"p99={med['p99']:5.2f}s")

    # ---- GPPPO grid ----
    print(f"\nRunning {len(betas)*len(Hs)} GPPPO configs...")
    for beta, H in product(betas, Hs):
        label = f"GPPPO(β={beta},H={H})"
        factory = _factory_for_gpppo(beta, H)
        save = (beta == args.canonical_beta and H == args.canonical_h)
        metrics, histories = _run_config(args, factory, label, seeds,
                                          workload_fn, drift_at, out_dir,
                                          save_traces=save,
                                          service_drift_fn=service_drift_fn,
                                          windows=windows)
        all_results.extend(metrics)
        if save and seeds:
            canonical_history = histories[seeds[0]]
        if args.verbose:
            med = {
                "cost": np.median([m["cost"] for m in metrics]),
                "viol": np.median([m["sla_violation_rate"] for m in metrics]),
                "p99":  np.median([m["p99_rt"] for m in metrics]),
            }
            print(f"  {label:22s} → cost={med['cost']:6.0f}  "
                  f"viol={100*med['viol']:5.1f}%  p99={med['p99']:5.2f}s")

    runtime = time.time() - t0
    print(f"\nSweep done in {runtime:.1f}s ({len(all_results)} simulations).")

    # ---- Aggregate per label ----
    summary = {}
    for r in all_results:
        summary.setdefault(r["label"], []).append(r)
    agg = []
    win_names = list(windows.keys())
    for label, runs in summary.items():
        a = {
            "label": label,
            "cost":  float(np.median([r["cost"] for r in runs])),
            "viol":  float(np.median([r["sla_violation_rate"] for r in runs])),
            "p99":   float(np.median([r["p99_rt"] for r in runs])),
            "tail":  float(np.median([r["tail_exceedance"] for r in runs])),
            "cores_mean": float(np.median([r["cores_mean"] for r in runs])),
            "cores_std":  float(np.median([r["cores_std"]  for r in runs])),
        }
        # Window medians (if available)
        for wn in win_names:
            wruns = [r["windowed"].get(wn, {}) for r in runs if "windowed" in r]
            if not wruns or not wruns[0]:
                continue
            a[f"{wn}_viol"] = float(np.median([w.get("viol_rate", float("nan")) for w in wruns]))
            a[f"{wn}_cost"] = float(np.median([w.get("cost", float("nan")) for w in wruns]))
            a[f"{wn}_cores"] = float(np.median([w.get("avg_cores", float("nan")) for w in wruns]))
            a[f"{wn}_p99"]   = float(np.median([w.get("p99_rt", float("nan")) for w in wruns]))
        agg.append(a)

    # ---- Pareto frontier on STEADY-STATE viol (more honest under drift) ----
    gpppo_pts = [a for a in agg if a["label"].startswith("GPPPO")]
    rank_field_viol = "steady_viol" if "steady" in win_names and \
                      all("steady_viol" in p for p in gpppo_pts) else "viol"
    rank_field_cost = "steady_cost" if "steady" in win_names and \
                      all("steady_cost" in p for p in gpppo_pts) else "cost"
    pareto = []
    for p in sorted(gpppo_pts, key=lambda a: a[rank_field_cost]):
        if not pareto or p[rank_field_viol] < pareto[-1][rank_field_viol]:
            pareto.append(p)
    pareto_labels = {p["label"] for p in pareto}

    # ---- Render table ----
    print()
    print("=" * 96)
    print(f"  PARETO SWEEP SUMMARY   plant={args.plant_model}   workload={args.workload}   "
          f"service_drift={args.service_drift}")
    print(f"  Windows: " + "  ".join(f"{n}=[{s},{e})" for n, (s, e) in windows.items()))
    print("=" * 96)

    baselines = [a for a in agg if not a["label"].startswith("GPPPO")]
    gpppo_sorted = sorted(gpppo_pts, key=lambda a: a[rank_field_cost])

    # Table 1: WHOLE-RUN metrics (legacy view)
    print(f"\n  ── WHOLE-RUN metrics (whole 0..{args.n_ticks}) ──")
    print(f"  {'config':25s}  {'cost':>6}  {'viol%':>6}  {'p99':>6}  {'tail':>7}  {'mean_c':>6}")
    print("  " + "-" * 76)
    for a in baselines + gpppo_sorted:
        print(f"  {a['label']:25s}  {a['cost']:6.0f}  {100*a['viol']:5.1f}%  "
              f"{a['p99']:6.2f}  {a['tail']:7.2f}  {a['cores_mean']:6.2f}")

    # Table 2: WINDOWED — steady-state focus (the honest one)
    if "steady" in win_names:
        print(f"\n  ── WINDOWED metrics (pre / transient / steady) — Pareto computed on STEADY ──")
        cols = ['config', 'pre_v%', 'tran_v%', 'STEADY_v%', 'STEADY_cost', 'STEADY_c', 'pareto']
        print(f"  {cols[0]:25s}  {cols[1]:>6}  {cols[2]:>7}  {cols[3]:>10}  "
              f"{cols[4]:>11}  {cols[5]:>8}  {cols[6]}")
        print("  " + "-" * 84)
        for a in baselines + gpppo_sorted:
            on_pareto = "★ PARETO" if a["label"] in pareto_labels else (
                "baseline" if not a["label"].startswith("GPPPO") else "")
            pre_v = a.get("pre_viol", float("nan"))
            tr_v  = a.get("transient_viol", float("nan"))
            st_v  = a.get("steady_viol", float("nan"))
            st_c  = a.get("steady_cost", float("nan"))
            st_co = a.get("steady_cores", float("nan"))
            print(f"  {a['label']:25s}  {100*pre_v:5.1f}%  {100*tr_v:6.1f}%  "
                  f"{100*st_v:9.1f}%  {st_c:11.0f}  {st_co:8.2f}  {on_pareto}")
    print("=" * 96)

    with open(out_dir / "summary.txt", "w") as f:
        # Re-emit table to file
        f.write(f"Pareto sweep: plant={args.plant_model}, workload={args.workload}, n_seeds={len(seeds)}\n")
        f.write(f"PI tuned: BC={args.bc}, DC={args.dc}, error={args.error_form}, deadband={args.rt_deadband_frac}\n\n")
        f.write(f"{'config':25s}  {'cost':>6}  {'viol%':>6}  {'p99':>6}  {'tail':>7}  {'mean_c':>6}  {'std_c':>6}  pareto\n")
        for a in baselines + gpppo_sorted:
            on_pareto = "PARETO" if a["label"] in pareto_labels else ("baseline" if not a["label"].startswith("GPPPO") else "")
            f.write(f"{a['label']:25s}  {a['cost']:6.0f}  {100*a['viol']:5.1f}%  "
                    f"{a['p99']:6.2f}  {a['tail']:7.2f}  {a['cores_mean']:6.2f}  {a['cores_std']:6.2f}  {on_pareto}\n")

    # ---- Persist ----
    with open(out_dir / "summary.json", "w") as f:
        json.dump({"args": vars(args), "agg": agg, "pareto": list(pareto_labels),
                   "all_results": all_results}, f, indent=2, default=str)

    # ---- Plots ----
    _plot_pareto(agg, pareto_labels, args, out_dir / "pareto.png")
    if canonical_history is not None:
        _plot_trajectory(canonical_history, args, out_dir / "trajectory_canonical.png",
                         title=f"Canonical run: GPPPO(β={args.canonical_beta}, H={args.canonical_h}), seed={seeds[0]}")
    print(f"\nArtefacts: {out_dir}/")
    print(f"  - summary.txt / summary.json")
    print(f"  - pareto.png  ← cost vs viol% scatter with Pareto frontier")
    print(f"  - trajectory_canonical.png  ← drift + OOD annotated trajectory")


# ---------------------------------------------------------------------------
def _plot_pareto(agg, pareto_labels, args, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    fig, ax = plt.subplots(figsize=(10, 7))

    # Map H → color (viridis), β → marker
    h_grid = sorted({int(p["label"].split("H=")[-1].rstrip(")"))
                     for p in agg if "H=" in p["label"]})
    beta_grid = sorted({int(p["label"].split("β=")[-1].split(",")[0])
                        for p in agg if "β=" in p["label"]})
    h_cmap = plt.cm.viridis
    h_color = {H: h_cmap(i / max(1, len(h_grid)-1)) for i, H in enumerate(h_grid)}
    β_marker_pool = ["o", "s", "^", "D", "P", "X", "v", "*"]
    beta_marker = {b: β_marker_pool[i % len(β_marker_pool)] for i, b in enumerate(beta_grid)}

    # Plot GPPPO points
    for p in agg:
        if not p["label"].startswith("GPPPO"):
            continue
        beta = int(p["label"].split("β=")[-1].split(",")[0])
        H    = int(p["label"].split("H=")[-1].rstrip(")"))
        c = h_color[H]
        m = beta_marker[beta]
        is_pareto = p["label"] in pareto_labels
        ax.scatter(p["cost"], 100*p["viol"], c=[c], marker=m, s=130 if is_pareto else 80,
                   edgecolors=("red" if is_pareto else "black"),
                   linewidths=2 if is_pareto else 0.5,
                   alpha=0.95)
        # annotate β=,H= on the point
        ax.annotate(f"β={beta} H={H}", (p["cost"], 100*p["viol"]),
                    xytext=(5, 5), textcoords="offset points", fontsize=7,
                    color="dimgray")

    # Plot baselines
    for p in agg:
        if p["label"].startswith("GPPPO"):
            continue
        if "PPO solo" in p["label"]:
            ax.scatter(p["cost"], 100*p["viol"], c="black", marker="*", s=320,
                       label=p["label"], edgecolors="white", linewidths=1.5, zorder=10)
        elif "PPO+PI" in p["label"]:
            ax.scatter(p["cost"], 100*p["viol"], c="darkred", marker="D", s=200,
                       label=p["label"], edgecolors="white", linewidths=1.5, zorder=10)

    # Pareto frontier line
    pareto_pts = sorted([p for p in agg if p["label"] in pareto_labels],
                         key=lambda a: a["cost"])
    if len(pareto_pts) >= 2:
        ax.plot([p["cost"] for p in pareto_pts],
                [100*p["viol"] for p in pareto_pts],
                "r--", lw=2, alpha=0.6, label="Pareto frontier (GPPPO)")

    # Legends: H by color, β by shape
    h_legend = [Patch(facecolor=h_color[H], edgecolor="black", label=f"H={H}") for H in h_grid]
    ax.legend(handles=ax.get_legend().legend_handles + h_legend,
              loc="upper right", fontsize=9) if ax.get_legend() else \
        ax.legend(handles=h_legend, loc="upper right", fontsize=9)

    ax.set_xlabel("Cost (Σ cores·dt)")
    ax.set_ylabel("SLA violation rate (%)")
    title = (f"GPPPO Pareto sweep — plant={args.plant_model}, "
             f"workload={args.workload} (λ={args.lam_pre}→{args.lam_post}), "
             f"n_seeds={len(args.seeds.split(','))}")
    ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()


def _plot_trajectory(history, args, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ts = [h["t"] for h in history]
    lams = [h["lambda"] for h in history]
    rts = [h["rt"] for h in history]
    cores = [h["cores"] for h in history]
    viol = [h["sla_violated"] for h in history]

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True,
                              gridspec_kw={"height_ratios": [1, 1.5, 1]})

    # Panel 1: λ(t) with training-range shading + drift annotation
    axes[0].plot(ts, lams, color="navy", lw=1.5)
    axes[0].axhspan(TRAIN_LAM_MIN, TRAIN_LAM_MAX, alpha=0.15, color="green",
                    label=f"PPO training range λ∈[{TRAIN_LAM_MIN:.0f}, {TRAIN_LAM_MAX:.0f}]")
    drift_marks = []
    if args.workload == "step":
        drift_marks = [(args.drift_at, "DRIFT (OOD)")]
    elif args.workload == "recurring_step":
        for i, dp in enumerate(args.recurring_drifts.split(",")):
            label = f"drift {i+1}"
            drift_marks.append((int(dp), label))
    for ax in axes:
        for dp, _ in drift_marks:
            ax.axvline(dp, color="red", ls="--", lw=1.0, alpha=0.5)
    for dp, label in drift_marks:
        axes[0].annotate(label, xy=(dp, max(lams)), xytext=(dp+5, max(lams)*0.9),
                         fontsize=9, color="red", fontweight="bold")
    axes[0].set_ylabel("λ (req/s)")
    axes[0].legend(loc="upper left", fontsize=9)
    axes[0].grid(alpha=0.3)

    # Panel 2: RT(t) on log scale + SLA line
    axes[1].plot(ts, rts, color="C3", lw=1.0, alpha=0.8, label="RT")
    axes[1].axhline(args.sla, color="black", ls="--", lw=1.2, label=f"SLA = {args.sla}s")
    axes[1].set_yscale("log")
    axes[1].set_ylabel("RT (s, log)")
    axes[1].legend(loc="upper left", fontsize=9)
    axes[1].grid(alpha=0.3)

    # Panel 3: cores(t) + violation rugplot
    axes[2].plot(ts, cores, color="C0", lw=1.5, drawstyle="steps-post", label="cores")
    # Violation rug at the bottom
    viol_ts = [t for t, v in zip(ts, viol) if v]
    if viol_ts:
        ymin = axes[2].get_ylim()[0]
        axes[2].scatter(viol_ts, [ymin]*len(viol_ts), color="red", marker="|", s=80,
                         label=f"SLA violation ({sum(viol)}/{len(viol)} ticks)")
    axes[2].set_xlabel("tick (s)")
    axes[2].set_ylabel("cores")
    axes[2].legend(loc="upper left", fontsize=9)
    axes[2].grid(alpha=0.3)

    fig.suptitle(title, fontsize=12, y=1.00)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()


if __name__ == "__main__":
    main()
