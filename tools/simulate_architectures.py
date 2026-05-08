#!/usr/bin/env python
"""Synthetic-plant simulator for autoscaling architecture comparison.

Compares 4 controller architectures on M/M/c-style synthetic workloads
WITHOUT requiring Locust/Docker. PPO/GPPPO are loaded from current code
(no checkpoints, cold-start training).

Quick examples
--------------

    # Default: step drift, 3 seeds, all 4 architectures, 300 ticks
    python tools/simulate_architectures.py

    # PPO frozen at t=150 (before drift) — tests "PPO trained then drift hits"
    python tools/simulate_architectures.py --train-freeze-at 150

    # Add cyclic + cyclic_step workloads, save plots
    python tools/simulate_architectures.py \\
        --workloads step,cyclic_step --plot

    # Only A1 vs A4 head-to-head, 5 seeds
    python tools/simulate_architectures.py \\
        --architectures A1_ppo,A4_gpppo --seeds 0,1,2,3,4

Reads
-----
    controllers/{ppocontroller,gpppo_controller,controltheoretical,controller}.py

Writes
------
    .claude/tmp/sim_out/<run-tag>/
        summary.txt          ASCII tables (printed to stdout too)
        summary.json         all metrics for all (arch × workload × seed)
        <wl>_<arch>_seed<N>.csv  per-run trajectory
        <wl>_<arch>_seed<N>.png  per-run plot (if --plot)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# Make `simulator` importable
_HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(_HERE))

from simulator.architectures import ARCHITECTURES  # noqa: E402
from simulator.metrics import compute_metrics       # noqa: E402
from simulator.runner import simulate_one           # noqa: E402
from simulator.workloads import WORKLOADS           # noqa: E402


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--architectures",
                   default="A1_ppo,A2_pi,A3_ppopi,A4_gpppo",
                   help="comma list (default: all 4). Available: %s" % ",".join(ARCHITECTURES))
    p.add_argument("--workloads", default="step",
                   help="comma list. Available: %s" % ",".join(WORKLOADS))
    p.add_argument("--seeds", default="0,1,2",
                   help="comma list of integer seeds (default: 0,1,2)")
    p.add_argument("--n-ticks", type=int, default=300)
    # ----- defaults aligned with training config exp-tweet_gpppo (sla=0.25, st=1.0,
    # min_cores=0.5, max_cores=28, init_cores=1) so the pre-trained PPO checkpoint
    # at controllers/ppocontroller-none.pt sees in-distribution state vectors.
    p.add_argument("--sla", type=float, default=0.25)
    p.add_argument("--noise-std", type=float, default=0.10,
                   help="multiplicative noise on RT (default: 0.10 = 10%%)")
    p.add_argument("--noise-dist", type=str, default="gaussian",
                   choices=("gaussian", "lognormal", "pareto", "rho_amplified"),
                   help="noise distribution (only for plant-model=fluid): gaussian, "
                        "lognormal, pareto, rho_amplified")
    p.add_argument("--plant-model", type=str, default="fluid",
                   choices=("fluid", "mmc"),
                   help="fluid: closed-form M/M/1-with-effective-rate (fast, "
                        "deterministic + multiplicative noise). mmc: discrete-event "
                        "M/M/c with Poisson arrivals + exponential service "
                        "(slower, intrinsic stochasticity, no noise param).")
    p.add_argument("--bc", type=float, default=None,
                   help="PI integral gain (override factory default 5.0). "
                        "Use values from `tune_pi.py`.")
    p.add_argument("--dc", type=float, default=None,
                   help="PI proportional gain (override factory default 10.0).")
    p.add_argument("--service-rate", type=float, default=10.0,
                   help="μ per core, in req/s (default: 10)")
    p.add_argument("--init-cores", type=float, default=1.0)
    p.add_argument("--min-cores", type=float, default=0.5)
    p.add_argument("--max-cores", type=float, default=28.0)
    p.add_argument("--st", type=float, default=1.0)
    p.add_argument("--period", type=int, default=1)
    p.add_argument("--train", dest="train", action="store_true",
                   help="Allow PPO to update its weights online (default: frozen).")
    p.add_argument("--no-train", dest="train", action="store_false",
                   help="Freeze PPO weights (use pre-trained checkpoint as-is).")
    p.set_defaults(train=False)
    p.add_argument("--train-freeze-at", type=int, default=None,
                   help="If --train is set, freeze PPO at this tick (e.g. 150 to "
                        "test 'trained-then-drift-hits' scenario)")
    p.add_argument("--drift-at", type=int, default=200,
                   help="tick at which step/cyclic_step drift fires (default: 200)")
    p.add_argument("--lam-pre", type=float, default=22.0,
                   help="λ before drift for step workload (default: 22 = training mean)")
    p.add_argument("--lam-post", type=float, default=80.0,
                   help="λ after drift for step workload (default: 80 = out of training range)")
    p.add_argument("--output-dir", default=".claude/tmp/sim_out",
                   help="root output dir (a timestamped subdir is created)")
    p.add_argument("--plot", action="store_true",
                   help="save matplotlib trajectories per run")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _format_table(rows, cols, widths) -> str:
    head = " | ".join(c.ljust(w) for c, w in zip(cols, widths))
    sep = "-" * len(head)
    lines = [head, sep]
    for row in rows:
        lines.append(" | ".join(str(v).ljust(w) for v, w in zip(row, widths)))
    return "\n".join(lines)


def aggregate(results, drift_at):
    """Collapse per-seed runs into median + IQR per (arch × workload)."""
    by_key: dict[tuple[str, str], list[dict]] = {}
    for r in results:
        by_key.setdefault((r["workload"], r["architecture"]), []).append(r)

    summary = []
    for (wl, arch), runs in sorted(by_key.items()):
        def med(field):
            vals = [r[field] for r in runs if field in r]
            return float(np.median(vals)) if vals else float("nan")

        summary.append({
            "workload": wl, "architecture": arch, "n_seeds": len(runs),
            "cost": med("cost"),
            "sla_violation_rate": med("sla_violation_rate"),
            "p95_rt": med("p95_rt"),
            "p99_rt": med("p99_rt"),
            "avg_rt": med("avg_rt"),
            "avg_cores": med("avg_cores"),
            "tail_exceedance": med("tail_exceedance"),
            "max_burst_len": med("max_burst_len"),
            "post_drift_sla_v_rate": med("post_drift_sla_v_rate"),
            "post_drift_avg_cores":  med("post_drift_avg_cores"),
            "time_to_recovery": med("time_to_recovery"),
        })
    return summary


def render_summary(summary, drift_at):
    lines = []
    workloads = sorted({s["workload"] for s in summary})
    for wl in workloads:
        lines.append(f"\n=== Workload: {wl.upper()}  (drift at t={drift_at}) ===")
        cols = ["arch",     "cost", "viol%",  "avg_rt", "p95_rt", "p99_rt",
                "tail_AUC", "burst", "avg_c"]
        widths = [12,         7,      7,        8,         8,         8,
                  9,           6,       6]
        rows = []
        for s in [x for x in summary if x["workload"] == wl]:
            rows.append([
                s["architecture"],
                f"{s['cost']:.0f}",
                f"{100 * s['sla_violation_rate']:.1f}%",
                f"{s['avg_rt']:.3f}",
                f"{s['p95_rt']:.3f}",
                f"{s['p99_rt']:.3f}",
                f"{s['tail_exceedance']:.2f}",
                f"{int(s['max_burst_len'])}",
                f"{s['avg_cores']:.2f}",
            ])
        lines.append(_format_table(rows, cols, widths))
    lines.append("\nLegend: cost=Σcores·dt, viol%=fraction of ticks above SLA, "
                 "avg/p95/p99 RT=quantiles of RT(s), tail_AUC=∫max(0,rt-sla)dt, "
                 "burst=longest run of consecutive viol, avg_c=avg cores.")
    return "\n".join(lines)


def save_csv(history, path):
    with open(path, "w") as f:
        f.write("t,lambda,rt,rho,cores,sla_violated\n")
        for h in history:
            f.write(f"{h['t']},{h['lambda']:.3f},{h['rt']:.4f},"
                    f"{h['rho']:.3f},{h['cores']:.2f},{int(h['sla_violated'])}\n")


def save_pareto_plot(results, path, title="Pareto: cost vs SLA violation rate"):
    """Scatter (cost, sla_violation_rate) per (arch × seed). One marker per run."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    archs = sorted({r["architecture"] for r in results})
    workloads = sorted({r["workload"] for r in results})
    cmap = plt.cm.tab10
    color_for = {a: cmap(i % 10) for i, a in enumerate(archs)}
    marker_for = {w: m for w, m in zip(workloads, ["o", "s", "^", "D", "v", "*", "P", "X"])}

    fig, ax = plt.subplots(figsize=(8, 6))
    for arch in archs:
        for wl in workloads:
            pts = [r for r in results if r["architecture"] == arch and r["workload"] == wl]
            if not pts:
                continue
            xs = [r["cost"] for r in pts]
            ys = [100 * r["sla_violation_rate"] for r in pts]
            ax.scatter(xs, ys, color=color_for[arch], marker=marker_for[wl],
                       label=f"{arch} ({wl})" if len(workloads) > 1 else arch,
                       s=80, alpha=0.7, edgecolors="black", linewidths=0.5)
            # also plot the median across seeds as a big star
            import numpy as np
            ax.scatter([np.median(xs)], [np.median(ys)], color=color_for[arch],
                       marker="*", s=300, edgecolors="black", linewidths=1.2, zorder=5)

    ax.set_xlabel("Cost (Σ cores·dt)")
    ax.set_ylabel("SLA violation rate (%)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    # invert y so "better" points (lower viol, lower cost) are top-left
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()


def save_plot(history, path, title, sla, drift_at=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ts = [h["t"] for h in history]
    fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
    axes[0].plot(ts, [h["lambda"] for h in history], color="gray", lw=1.2)
    axes[0].set_ylabel("λ (req/s)")
    axes[0].set_title(title)
    axes[1].plot(ts, [h["rt"] for h in history], color="C3", lw=1.0)
    axes[1].axhline(sla, color="black", ls="--", lw=0.8, label=f"SLA={sla}s")
    axes[1].set_yscale("log")
    axes[1].set_ylabel("RT (s, log)")
    axes[1].legend(loc="upper right")
    axes[2].plot(ts, [h["cores"] for h in history], color="C0", lw=1.2,
                 drawstyle="steps-post")
    axes[2].set_ylabel("cores")
    axes[2].set_xlabel("tick")
    if drift_at is not None:
        for ax in axes:
            ax.axvline(drift_at, color="orange", ls=":", lw=0.8, alpha=0.7)
    plt.tight_layout()
    plt.savefig(path, dpi=110)
    plt.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    arch_list = [a.strip() for a in args.architectures.split(",")]
    wl_list = [w.strip() for w in args.workloads.split(",")]
    seeds = [int(s) for s in args.seeds.split(",")]

    for a in arch_list:
        if a not in ARCHITECTURES:
            sys.exit(f"unknown architecture: {a!r}. Choices: {list(ARCHITECTURES)}")
    for w in wl_list:
        if w not in WORKLOADS:
            sys.exit(f"unknown workload: {w!r}. Choices: {list(WORKLOADS)}")

    tag = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.output_dir) / f"sim-{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    total = len(arch_list) * len(wl_list) * len(seeds)
    done = 0
    t_start = time.time()

    for wl_name in wl_list:
        wl_fn_raw = WORKLOADS[wl_name]
        # bind drift_at + lam params for step / cyclic_step
        if wl_name == "step":
            wl_fn = lambda t, _f=wl_fn_raw: _f(t, lam_pre=args.lam_pre,
                                               lam_post=args.lam_post,
                                               drift_at=args.drift_at)
        elif wl_name == "cyclic_step":
            wl_fn = lambda t, _f=wl_fn_raw: _f(t, drift_at=args.drift_at)
        else:
            wl_fn = wl_fn_raw

        for arch_name in arch_list:
            label, factory = ARCHITECTURES[arch_name]
            for seed in seeds:
                done += 1
                t_run = time.time()
                if args.verbose:
                    print(f"  [{done}/{total}] {arch_name:10s} on {wl_name:12s} seed={seed} ...",
                          end="", flush=True)
                log_path = out_dir / f"{wl_name}_{arch_name}_seed{seed}.log"
                extra = {}
                if args.bc is not None: extra["BC"] = args.bc
                if args.dc is not None: extra["DC"] = args.dc
                history = simulate_one(
                    factory, wl_fn,
                    n_ticks=args.n_ticks, sla=args.sla,
                    service_rate=args.service_rate,
                    noise_std=args.noise_std,
                    noise_dist=args.noise_dist,
                    init_cores=args.init_cores, min_cores=args.min_cores,
                    max_cores=args.max_cores, st=args.st, period=args.period,
                    train=args.train,
                    train_freeze_at=args.train_freeze_at, seed=seed,
                    log_path=log_path,
                    plant_model=args.plant_model,
                    extra_common=extra if extra else None,
                )
                drift_t = args.drift_at if wl_name in ("step", "cyclic_step") else None
                m = compute_metrics(history, sla=args.sla, drift_at=drift_t)
                m.update({"architecture": arch_name, "workload": wl_name,
                          "seed": seed, "label": label})
                results.append(m)

                save_csv(history, out_dir / f"{wl_name}_{arch_name}_seed{seed}.csv")
                if args.plot:
                    save_plot(history,
                              out_dir / f"{wl_name}_{arch_name}_seed{seed}.png",
                              title=f"{arch_name} ({label}) on {wl_name} (seed {seed})",
                              sla=args.sla, drift_at=drift_t)
                if args.verbose:
                    print(f" {time.time() - t_run:5.1f}s  "
                          f"cost={m['cost']:.0f}  sla_v={m['sla_violation_rate']:.1%}",
                          flush=True)

    summary = aggregate(results, args.drift_at)
    rendered = render_summary(summary, args.drift_at)

    print(rendered)

    # Always save Pareto plot — key visual for paper sharing
    pareto_path = out_dir / "pareto.png"
    title = (f"Pareto: cost vs SLA viol — λ={args.lam_pre}→{args.lam_post}"
             if "step" in wl_list else
             f"Pareto: cost vs SLA viol — workloads={','.join(wl_list)}")
    save_pareto_plot(results, pareto_path, title=title)
    print(f"Pareto plot: {pareto_path}")
    print(f"\nTotal time: {time.time() - t_start:.1f}s. Results in {out_dir.resolve()}/")

    with open(out_dir / "summary.txt", "w") as f:
        f.write(rendered + "\n")
    with open(out_dir / "summary.json", "w") as f:
        json.dump({"args": vars(args), "results": results, "summary": summary},
                  f, indent=2, default=str)

    # Pretty key=value config for human review
    with open(out_dir / "config.txt", "w") as f:
        for k, v in sorted(vars(args).items()):
            f.write(f"{k} = {v}\n")


if __name__ == "__main__":
    main()
