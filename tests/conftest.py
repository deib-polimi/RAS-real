"""Shared pytest fixtures for RAS-real tests.

Kept intentionally lean: this codebase runs in cloud VMs and we test behaviour,
not getters. Add fixtures here only when re-used across ≥2 test files.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest


@dataclass
class MockMonitoring:
    """Minimal stand-in for monitoring.Monitoring used by controllers in tests.

    Override per-test by setting attributes directly. Use ``feed`` to script a
    sequence of RT values returned on successive ``getRT``/``getRTp95`` calls.
    """

    rt: float = 0.5
    rt_p95: float = 0.5
    queue_len: int = 0
    arrival_rate: float = 0.0
    users: int = 0
    rt_sequence: list[float] = field(default_factory=list)

    def feed(self, sequence: list[float]) -> None:
        self.rt_sequence = list(sequence)

    def _next(self) -> float:
        if self.rt_sequence:
            return self.rt_sequence.pop(0)
        return self.rt

    def getRT(self) -> float:
        return self._next()

    def getRTp95(self) -> float:
        return self.rt_p95

    def getQueueLen(self) -> int:
        return self.queue_len

    def getArrivalRate(self) -> float:
        return self.arrival_rate

    def getUsers(self) -> int:
        return self.users


@pytest.fixture
def mock_monitoring() -> MockMonitoring:
    return MockMonitoring()
