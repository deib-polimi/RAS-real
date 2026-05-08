"""Aggregate metrics over a simulation history."""
from __future__ import annotations

from typing import Sequence

import numpy as np


def _window_metrics(rts: np.ndarray, cores: np.ndarray, sla_v: np.ndarray,
                    sla: float) -> dict:
    """Metrics inside an arbitrary window (sliced by caller)."""
    if len(rts) == 0:
        return {}
    tail_ex = float(np.sum(np.maximum(0.0, rts - sla)))
    return {
        "n_ticks":      int(len(rts)),
        "viol_rate":    float(np.mean(sla_v)),
        "n_violations": int(np.sum(sla_v)),
        "avg_rt":       float(np.mean(rts)),
        "p95_rt":       float(np.percentile(rts, 95)),
        "p99_rt":       float(np.percentile(rts, 99)),
        "max_rt":       float(np.max(rts)),
        "avg_cores":    float(np.mean(cores)),
        "max_cores":    float(np.max(cores)),
        "cost":         float(np.sum(cores)),
        "tail_AUC":     tail_ex,
    }


def windowed_metrics(history: Sequence[dict], sla: float,
                     windows: dict[str, tuple]) -> dict:
    """Compute metrics in arbitrary named windows.

    windows = {"pre": (start, end), "transient": (s, e), "steady": (s, e), ...}
    """
    rts   = np.array([h["rt"] for h in history])
    cores = np.array([h["cores"] for h in history])
    sla_v = np.array([h["sla_violated"] for h in history])

    out = {}
    for name, (s, e) in windows.items():
        s = max(0, int(s)) if s is not None else 0
        e = min(len(history), int(e)) if e is not None else len(history)
        if s >= e:
            out[name] = {}
            continue
        out[name] = _window_metrics(rts[s:e], cores[s:e], sla_v[s:e], sla)
    return out


def compute_metrics(history: Sequence[dict], sla: float = 0.2,
                    drift_at: int | None = None) -> dict:
    """Per-run scalar metrics."""
    rts = np.array([h["rt"] for h in history])
    cores = np.array([h["cores"] for h in history])
    sla_v = np.array([h["sla_violated"] for h in history])

    # SLA-shortfall area: ∫ max(0, rt - sla) dt — total tail-driven exceedance
    tail_exceedance = np.maximum(0.0, rts - sla)

    # Burst count: maximal runs of consecutive violations
    bursts = []
    run = 0
    for v in sla_v:
        if v:
            run += 1
        else:
            if run > 0:
                bursts.append(run)
            run = 0
    if run > 0:
        bursts.append(run)

    metrics = {
        "n_ticks": int(len(history)),
        "sla_violation_rate": float(np.mean(sla_v)),
        "n_violations": int(np.sum(sla_v)),
        "avg_rt": float(np.mean(rts)),
        "p95_rt": float(np.percentile(rts, 95)),
        "p99_rt": float(np.percentile(rts, 99)),
        "max_rt": float(np.max(rts)),
        "avg_cores": float(np.mean(cores)),
        "max_cores": float(np.max(cores)),
        "cost": float(np.sum(cores)),     # ∫ cores dt with dt=1
        "tail_exceedance": float(np.sum(tail_exceedance)),  # ∫ max(0, rt - sla) dt
        "n_bursts": int(len(bursts)),
        "max_burst_len": int(max(bursts)) if bursts else 0,
        "p99_excess_ratio": float(max(0.0, np.percentile(rts, 99) / sla - 1.0)),
    }

    if drift_at is not None and drift_at < len(history):
        post = history[drift_at:]
        # time-to-recovery: ticks until RT drops below SLA after drift onset
        recovery = None
        for offset, h in enumerate(post):
            if h["rt"] <= sla:
                # require 5 consecutive recovered ticks for stability
                window = post[offset: offset + 5]
                if len(window) == 5 and all(w["rt"] <= sla for w in window):
                    recovery = offset
                    break
        metrics["time_to_recovery"] = recovery if recovery is not None else len(post)
        # split metrics: pre vs post drift
        pre = history[:drift_at]
        metrics["pre_drift_sla_v_rate"] = float(np.mean([h["sla_violated"] for h in pre]))
        metrics["post_drift_sla_v_rate"] = float(np.mean([h["sla_violated"] for h in post]))
        metrics["pre_drift_avg_cores"]  = float(np.mean([h["cores"] for h in pre]))
        metrics["post_drift_avg_cores"] = float(np.mean([h["cores"] for h in post]))

    return metrics
