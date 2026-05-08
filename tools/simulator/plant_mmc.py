"""Discrete-event M/M/c plant.

True open M/M/c queueing system:
  - arrivals: Poisson(λ) — exponential inter-arrival times
  - service:  c parallel servers, each with exponential(μ) service time
  - queue:    FIFO, unbounded

Each step() simulates 1 second of operation, processes all events in time
order via a heap, and reports the mean RT of requests COMPLETED during the
tick. Servers are integers (cores rounded to int).

Compatible with `SyntheticMonitoring` and `runner.simulate_one()` — same
public surface as `plant.MMcPlant` (last_rt / last_lambda / last_cores /
last_rho attributes).
"""
from __future__ import annotations

import heapq

import numpy as np


class MMcDiscretePlant:
    """Open M/M/c queue with stochastic Poisson/exponential dynamics."""

    def __init__(
        self,
        service_rate: float = 10.0,    # μ per server (req/s)
        sla: float = 0.25,
        rt_saturation: float = 5.0,    # cap when system is overloaded
        rng: np.random.Generator | None = None,
        # API compatibility with MMcPlant — these are accepted but ignored;
        # discrete-event has intrinsic stochasticity from M/M assumptions.
        noise_std: float = 0.0,
        noise_dist: str = "intrinsic",
        pareto_alpha: float = 2.0,
        service_drift_fn=None,         # callable(t) → multiplier on μ
    ):
        self.service_rate = service_rate
        self.sla = sla
        self.rt_saturation = rt_saturation
        self.rng = rng if rng is not None else np.random.default_rng(0)
        self.service_drift_fn = service_drift_fn

        # Internal state
        self.now: float = 0.0                      # simulated wall-clock (s)
        self.busy: list[tuple[float, float]] = []  # min-heap of (departure_time, arrival_time)
        self.queue: list[float] = []               # FIFO of waiting arrival times
        self.next_arrival: float | None = None     # scheduled arrival time
        self._first_step = True

        # Public state (read by SyntheticMonitoring)
        self.last_rt: float = 1.0 / service_rate   # idealized base
        self.last_lambda: float = 0.0
        self.last_cores: float = 1.0
        self.last_rho: float = 0.0

        # Ignored (kept for API parity)
        self.noise_dist = noise_dist
        self.noise_std = noise_std
        self.pareto_alpha = pareto_alpha

    # ------------------------------------------------------------------
    def _current_mu(self) -> float:
        if self.service_drift_fn is None:
            return self.service_rate
        factor = max(1e-6, float(self.service_drift_fn(self.now)))
        return self.service_rate * factor

    def _try_start_from_queue(self, c: int) -> None:
        """Start as many queued requests as we have free servers for."""
        mu = self._current_mu()
        while self.queue and len(self.busy) < c:
            arr = self.queue.pop(0)
            service_t = self.rng.exponential(1.0 / mu)
            heapq.heappush(self.busy, (self.now + service_t, arr))

    def step(self, arrival_rate: float, cores: float) -> float:
        c = max(1, int(round(float(cores))))
        lam = max(0.0, float(arrival_rate))
        tick_end = self.now + 1.0
        completed_rts: list[float] = []

        # On first call, schedule the first arrival
        if self._first_step:
            self._first_step = False
            self.next_arrival = (
                self.now + self.rng.exponential(1.0 / max(lam, 1e-9))
                if lam > 0 else None
            )

        # If λ changed since last tick, the OLD next_arrival was sampled with
        # the old rate. We accept this minor inaccuracy — the next inter-arrival
        # after this one will use the new rate.

        # If c increased, immediately start any queued backlog.
        self._try_start_from_queue(c)

        while True:
            next_dep = self.busy[0][0] if self.busy else float("inf")
            next_arr = self.next_arrival if self.next_arrival is not None else float("inf")
            evt_time = min(next_dep, next_arr)

            if evt_time >= tick_end:
                # No more events in this tick.
                self.now = tick_end
                break

            self.now = evt_time

            if next_dep <= next_arr:
                # ---- Service completion ----
                dep_time, arr_time = heapq.heappop(self.busy)
                completed_rts.append(dep_time - arr_time)
                # Try to start next from queue on the freed server
                self._try_start_from_queue(c)
            else:
                # ---- Arrival ----
                arr_time = next_arr
                # Schedule next arrival
                self.next_arrival = (
                    arr_time + self.rng.exponential(1.0 / max(lam, 1e-9))
                    if lam > 0 else None
                )
                # Place into service or queue
                if len(self.busy) < c:
                    mu = self._current_mu()
                    service_t = self.rng.exponential(1.0 / mu)
                    heapq.heappush(self.busy, (self.now + service_t, arr_time))
                else:
                    self.queue.append(arr_time)

        # ---- Measurement ----
        mu_eff = self._current_mu()
        if completed_rts:
            measured_rt = float(np.mean(completed_rts))
        else:
            ρ = lam / (c * mu_eff) if mu_eff > 0 else 0.0
            if ρ >= 1.0:
                measured_rt = self.rt_saturation
            elif self.queue:
                oldest_wait = self.now - self.queue[0]
                measured_rt = max(1.0 / mu_eff, oldest_wait)
            else:
                measured_rt = 1.0 / mu_eff

        self.last_rt = float(min(measured_rt, self.rt_saturation))
        self.last_lambda = lam
        self.last_cores = float(c)
        self.last_rho = lam / (c * mu_eff) if mu_eff > 0 else 0.0
        return self.last_rt
