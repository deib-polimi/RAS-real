"""M/M/1-with-effective-rate plant model for autoscaling controller testing.

Closed-form RT given (arrival_rate λ, cores c, service_rate μ):
    ρ = λ / (c · μ)
    if ρ ≥ 1 : RT = rt_saturation        (saturation cap)
    else     : RT = 1 / (c·μ − λ) · (1 + ε)
where ε is drawn from the configured noise distribution.

Noise distributions:
  - "gaussian": ε ~ N(0, σ). Symmetric, mean ≈ median ≈ p95.
  - "lognormal": rt = base·exp(N(0, σ)). Heavy positive tail; mean = base·exp(σ²/2).
  - "pareto":   ε = σ · (Pareto(α=2.0) − 1) clipped at 0; large rare positive shocks.
                Mean RT ≈ base; p95/p99 RT >> base (tail-driven SLA failures).
  - "rho_amplified": σ_eff = σ · (1 + 4·max(0, ρ−0.5)). Noise std GROWS with utilization
                ρ — simulates queue contention / co-tenant interference near saturation.
                STATE-DEPENDENT: GP can learn it via (prev_rt, cores_norm, prev_users).
"""
from __future__ import annotations

import numpy as np


class MMcPlant:
    """Single-class queueing plant for synthetic experiments."""

    def __init__(
        self,
        service_rate: float = 10.0,
        sla: float = 0.2,
        noise_std: float = 0.10,
        rt_saturation: float = 5.0,
        noise_dist: str = "gaussian",
        pareto_alpha: float = 2.0,
        rng: np.random.Generator | None = None,
        service_drift_fn=None,
    ):
        self.service_rate = service_rate
        self.sla = sla
        self.noise_std = noise_std
        self.rt_saturation = rt_saturation
        self.noise_dist = noise_dist
        self.pareto_alpha = pareto_alpha
        self.rng = rng if rng is not None else np.random.default_rng(0)
        self.service_drift_fn = service_drift_fn
        self._tick = 0

        self.last_rt = 0.0
        self.last_lambda = 0.0
        self.last_cores = 1.0
        self.last_rho = 0.0

    def _sample_noise(self, rho: float = 0.0) -> float:
        """Return a noise multiplier ε such that rt = base · (1 + ε)."""
        if self.noise_dist == "gaussian":
            return float(self.rng.normal(0.0, self.noise_std))
        if self.noise_dist == "lognormal":
            # rt = base * exp(N(0, σ)) → 1+ε = exp(N(0, σ)) → ε = exp(N(0,σ)) - 1
            return float(np.exp(self.rng.normal(0.0, self.noise_std)) - 1.0)
        if self.noise_dist == "pareto":
            # Shifted Pareto: shock = σ · (Pareto(α) − 1); positive heavy tail.
            x = self.rng.pareto(self.pareto_alpha)  # E[x] = 1/(α−1) for α>1
            return float(self.noise_std * x)        # rare large positive shocks
        if self.noise_dist == "rho_amplified":
            # State-dependent: noise grows as utilization ρ approaches saturation.
            # σ_eff = σ · (1 + 4·max(0, ρ−0.5)) so σ doubles at ρ=0.625 and 6× at ρ=1.
            amp = 1.0 + 4.0 * max(0.0, rho - 0.5)
            return float(self.rng.normal(0.0, self.noise_std * amp))
        raise ValueError(f"unknown noise_dist: {self.noise_dist}")

    def step(self, arrival_rate: float, cores: float) -> float:
        """Run one tick: compute RT given current λ and c. Updates `last_*`."""
        c = max(1.0, float(cores))
        lam = max(0.0, float(arrival_rate))
        mu_eff = self.service_rate
        if self.service_drift_fn is not None:
            mu_eff *= max(1e-6, float(self.service_drift_fn(self._tick)))
        capacity = c * mu_eff
        rho = lam / capacity
        self._tick += 1

        if rho >= 1.0:
            base_rt = self.rt_saturation
        else:
            base_rt = 1.0 / (capacity - lam)

        noise = self._sample_noise(rho)
        rt = max(0.001, base_rt * (1.0 + noise))

        self.last_rt = float(rt)
        self.last_lambda = lam
        self.last_cores = c
        self.last_rho = float(rho)
        return self.last_rt
