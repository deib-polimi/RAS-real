"""Service-rate drift functions: simulate UNOBSERVED capacity degradation.

Returns a multiplier on the base μ. The PPO controller does NOT see μ directly —
it only observes the resulting RT. This is the "hard" drift case where the
GP layer must learn to predict failures from RT/queue/features alone.

Realistic scenarios modelled:
  - step:    sudden μ collapse (GC pause, network hiccup, container co-tenant)
  - ramp:    progressive μ degradation (memory leak, cache pollution, thermal throttling)
  - bursty:  periodic ON/OFF degradation (scheduled GC, batch jobs)
"""
from __future__ import annotations


def none(t: float) -> float:
    """No service drift. μ_eff = μ."""
    return 1.0


def step(t: float, factor: float = 0.5, drift_at: float = 300.0) -> float:
    """μ halves at drift_at — failure-like sudden degradation."""
    return 1.0 if t < drift_at else factor


def ramp(t: float, factor_end: float = 0.5,
         ramp_start: float = 300.0, ramp_end: float = 900.0) -> float:
    """μ degrades linearly over [ramp_start, ramp_end] — server aging."""
    if t < ramp_start:
        return 1.0
    if t >= ramp_end:
        return factor_end
    frac = (t - ramp_start) / (ramp_end - ramp_start)
    return 1.0 - frac * (1.0 - factor_end)


def bursty(t: float, factor_low: float = 0.4, period: float = 200.0) -> float:
    """μ alternates 1.0 / factor_low every (period/2) ticks — periodic GC."""
    cycle = int(t // (period / 2))
    return float(factor_low) if (cycle % 2) == 1 else 1.0


SERVICE_DRIFTS = {
    "none":   none,
    "step":   step,
    "ramp":   ramp,
    "bursty": bursty,
}
