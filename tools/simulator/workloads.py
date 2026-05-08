"""Workload generators: λ(t) functions returning arrival rate at tick t."""
from __future__ import annotations

import numpy as np


def stationary(t: int, lam: float = 22.0) -> float:
    """Stationary λ. Default 22 = mean of TweetGen(bias=40, shift=10) training trace."""
    return float(lam)


def stationary15(t: int) -> float:
    return 15.0


def stationary22(t: int) -> float:
    return 22.0


def stationary30(t: int) -> float:
    return 30.0


def stationary40(t: int) -> float:
    return 40.0


def stationary50(t: int) -> float:
    return 50.0


def step(t: int, lam_pre: float = 30.0, lam_post: float = 50.0,
         drift_at: int = 200) -> float:
    return float(lam_post if t >= drift_at else lam_pre)


def cyclic(t: int, mean: float = 30.0, amp: float = 20.0,
           period: float = 100.0) -> float:
    return float(mean + amp * np.sin(2.0 * np.pi * t / period))


def cyclic_step(t: int, drift_at: int = 200, drift_size: float = 20.0) -> float:
    base = cyclic(t)
    if t >= drift_at:
        base += drift_size
    return float(base)


def recurring_step(t: int, lam_low: float = 22.0, lam_high: float = 80.0,
                   drift_points: tuple = (300, 600, 900)) -> float:
    """Recurring up/down drift: up @ drift[0], down @ drift[1], up @ drift[2], ...

    Default for 1200-tick runs:
      t < 300:  lam_low (warmup, in-distribution).
      300..599: lam_high (drift up, OOD).
      600..899: lam_low (drift down, back to in-distribution).
      900+:     lam_high (recurring drift up, OOD again).

    Tests: GP pre-drift training, OOD adaptation, re-adaptation, recurrence.
    """
    state = 0  # 0=low, 1=high
    for dp in drift_points:
        if t >= dp:
            state = 1 - state
    return float(lam_high if state == 1 else lam_low)


def linear_ramp(t: int, lam_start: float = 30.0, lam_end: float = 60.0,
                ramp_start: int = 100, ramp_end: int = 300) -> float:
    if t < ramp_start:
        return float(lam_start)
    if t >= ramp_end:
        return float(lam_end)
    frac = (t - ramp_start) / (ramp_end - ramp_start)
    return float(lam_start + frac * (lam_end - lam_start))


WORKLOADS = {
    "stationary": stationary,
    "stationary15": stationary15,
    "stationary22": stationary22,
    "stationary30": stationary30,
    "stationary40": stationary40,
    "stationary50": stationary50,
    "step": step,
    "cyclic": cyclic,
    "cyclic_step": cyclic_step,
    "linear_ramp": linear_ramp,
    "recurring_step": recurring_step,
}
