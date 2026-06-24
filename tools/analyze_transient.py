#!/usr/bin/env python3
"""Transient metrics for a load/drift experiment (settling time + violation area).

The right metric when the controller eventually RECOVERS: we care about how long
and how badly it violates during the transient after a disturbance — NOT the average.
(= the TCC 2024 settling-time framing.)

Usage:
  python3 tools/analyze_transient.py --glob "experiments/exp-azure-E1-*/data.mat" --sla 0.18 --drift 300
  python3 tools/analyze_transient.py --glob "experiments/exp-local-smoke-FC-*/data.mat" --sla 0.25 --drift 300

Groups runs by controller token (ppo/mmcpi/handover) parsed from the path.
"""
import argparse
import glob
import os
import re
import numpy as np
from scipy.io import loadmat

CTRLS = ("ppo", "mmcpi", "handover", "static")


def ctrl_of(path):
    for c in CTRLS:
        if re.search(rf"[-/]{c}[-/]", path) or path.rstrip("/").endswith(c):
            return c
    # fallback: token before timestamp
    base = os.path.basename(os.path.dirname(path))
    for c in CTRLS:
        if c in base:
            return c
    return base


def settling_time(t, rt, sla, drift, hold=15.0):
    """First time after `drift` from which p-avg RT stays <= SLA for >= `hold` s.
    Returns seconds-after-drift, or None if never settles before run end."""
    post = t >= drift
    tt, rr = t[post], rt[post]
    for i, tv in enumerate(tt):
        w = (tt >= tv) & (tt < tv + hold)
        if w.sum() > 0 and (rr[w] <= sla).all():
            return float(tv - drift)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", required=True)
    ap.add_argument("--sla", type=float, required=True)
    ap.add_argument("--drift", type=float, required=True)
    ap.add_argument("--hold", type=float, default=15.0,
                    help="seconds RT must stay <=SLA to count as settled")
    args = ap.parse_args()

    paths = sorted(glob.glob(args.glob))
    if not paths:
        print("no runs match", args.glob); return

    rows = {}
    for p in paths:
        d = loadmat(p)
        t = np.array(d["time"]).flatten()
        rt = np.array(d["rts"]).flatten()
        co = np.array(d["cores"]).flatten()
        pre = t < args.drift
        post = t >= args.drift
        # per-second integration weight (assume ~uniform sampling)
        dt = np.median(np.diff(t)) if len(t) > 1 else 1.0
        varea = float(np.maximum(0.0, rt[post] - args.sla).sum() * dt)
        rows[ctrl_of(p)] = {
            "path": p,
            "viol_pre": 100*(rt[pre] > args.sla).sum()/max(pre.sum(), 1),
            "viol_post": 100*(rt[post] > args.sla).sum()/max(post.sum(), 1),
            "p95_post": float(np.percentile(rt[post], 95)) if post.sum() else float("nan"),
            "peak_post": float(rt[post].max()) if post.sum() else float("nan"),
            "varea": varea,
            "settle": settling_time(t, rt, args.sla, args.drift, args.hold),
            "cores_pre": float(co[pre].mean()) if pre.sum() else float("nan"),
            "cores_post_max": float(co[post].max()) if post.sum() else float("nan"),
        }

    print(f"\nSLA={args.sla}s  drift@{args.drift}s  (settle = s to keep p-avg<=SLA for {args.hold}s)\n")
    h = f"{'ctrl':10s} {'viol_pre':>8s} {'viol_post':>9s} {'p95_post':>8s} {'peak':>6s} {'viol_area':>9s} {'settle_s':>8s} {'c_pre':>6s} {'c_post_max':>10s}"
    print(h); print("-"*len(h))
    for c in CTRLS:
        if c not in rows: continue
        r = rows[c]
        st = f"{r['settle']:.0f}" if r['settle'] is not None else ">end"
        print(f"{c:10s} {r['viol_pre']:7.1f}% {r['viol_post']:8.1f}% {r['p95_post']:8.3f} {r['peak_post']:6.2f} {r['varea']:9.2f} {st:>8s} {r['cores_pre']:6.2f} {r['cores_post_max']:10.0f}")

    # necessity verdict (PPO vs best physics)
    if "ppo" in rows:
        phys = [rows[c] for c in ("mmcpi", "handover") if c in rows]
        if phys:
            best = min(phys, key=lambda r: r["varea"])
            pv, bv = rows["ppo"]["varea"], best["varea"]
            ps = rows["ppo"]["settle"]; bs = best["settle"]
            print("\nNECESSITÀ (transitorio):")
            print(f"  violation_area: PPO={pv:.2f} vs physics={bv:.2f}  → {pv/max(bv,1e-9):.1f}× peggio" if bv else "")
            if ps is not None and bs is not None and bs > 0:
                print(f"  settling_time:  PPO={ps:.0f}s vs physics={bs:.0f}s  → {ps/bs:.1f}× più lento")


if __name__ == "__main__":
    main()
