"""Adapter exposing the `Monitoring` interface over the synthetic plant.

The real `monitoring.py` aggregates Locust events over a sliding window. Here we
back the same getters with the plant's last RT plus a small history buffer for
the percentile getter.
"""
from __future__ import annotations

from collections import deque

import numpy as np


class SyntheticMonitoring:
    """Mimics the public surface of `monitoring.Monitoring`."""

    def __init__(self, plant, history_size: int = 10, users: int = 50):
        self.plant = plant
        self.rt_history: deque[float] = deque(maxlen=history_size)
        self.users = users

    def update(self) -> None:
        """Call after `plant.step()` to refresh the rolling window."""
        self.rt_history.append(self.plant.last_rt)

    # ---- public API expected by controllers ------------------------------

    def getRT(self) -> float:
        if not self.rt_history:
            return 0.0
        return float(np.mean(self.rt_history))

    def getRTp95(self) -> float:
        if not self.rt_history:
            return 0.0
        if len(self.rt_history) == 1:
            return float(self.rt_history[0])
        return float(np.percentile(self.rt_history, 95))

    def getQueueLen(self) -> int:
        # Little's Law: L = λ · W
        return int(self.plant.last_lambda * self.plant.last_rt)

    def getArrivalRate(self) -> float:
        return float(self.plant.last_lambda)

    def getUsers(self) -> int:
        return int(self.users)
