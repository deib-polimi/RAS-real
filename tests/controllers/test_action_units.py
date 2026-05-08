"""Tests for GPPPOController action representation invariants."""
from __future__ import annotations

import sys
import os
import importlib.util

# ---------------------------------------------------------------------------
# Direct module loading to bypass controllers/__init__.py which imports casadi
# ---------------------------------------------------------------------------
_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
_CTRL_DIR = os.path.join(_REPO, "controllers")


def _load(name: str, path: str):
    """Load a module directly from its file, registering it under `name`."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # register before exec so circular imports resolve
    spec.loader.exec_module(mod)
    return mod


# Load in dependency order
_load("controllers.controller",    os.path.join(_CTRL_DIR, "controller.py"))
_load("controllers.circular",      os.path.join(_CTRL_DIR, "circular.py"))
_load("controllers.controltheoretical", os.path.join(_CTRL_DIR, "controltheoretical.py"))
_load("controllers.ppocontroller", os.path.join(_CTRL_DIR, "ppocontroller.py"))
_load("controllers.gpppo_controller", os.path.join(_CTRL_DIR, "gpppo_controller.py"))

from controllers.gpppo_controller import GPPPOController
from controllers.ppocontroller import PPOController

import numpy as np
import pytest


class _VariedMonitoring:
    """Monitoring that cycles through a varied RT sequence to force action diversity."""

    def __init__(self, rt_sequence: list[float]):
        self._seq = list(rt_sequence)
        self._idx = 0

    def _current(self) -> float:
        v = self._seq[self._idx % len(self._seq)]
        self._idx += 1
        return v

    def getRT(self) -> float:
        return self._current()

    def getRTp95(self) -> float:
        return self._current()

    def getQueueLen(self) -> int:
        return 0

    def getArrivalRate(self) -> float:
        return 0.0

    def getUsers(self) -> int:
        return 0


def _make_controller() -> GPPPOController:
    """Build a GPPPOController with thresholds small enough that the buffer fills quickly."""
    ctrl = GPPPOController(
        period=1,
        init_cores=4,
        min_cores=1,
        max_cores=20,
        st=0.8,
        train=True,
        bc=5,
        dc=10,
        gp_min_samples=5,
        gp_train_start=2,
        pi_start_time=2,
        enable_log=False,
    )
    ctrl.setSLA(0.25)  # setpoint = 0.25 * 0.8 = 0.20
    return ctrl


def test_gp_input_uses_delta_cores_not_action_index():
    """Invariant: The value stored at gp_data_buffer[i][0][0] must equal the
    delta cores that PPO actually applied on that tick (i.e. an element of
    {-2, -1, 0, 1, 2}), NOT the action index (0..4).

    Anti-degeneracy requires ALL of:
    1. Domain exclusion: values 3 and 4 must never appear (valid indices, invalid deltas).
    2. Negative values must appear at least once (indices are always >= 0).
    3. Equivalence: every dim0 value must be in the set of deltas actually produced.
    """
    ctrl = _make_controller()

    # Varied RT: alternating very-low and very-high to force the full action spread
    rt_values = [0.05, 1.5, 0.03, 2.0, 0.04, 1.8, 0.06, 0.5, 2.5, 0.02] * 10
    mon = _VariedMonitoring(rt_values)
    ctrl.setMonitoring(mon)

    # -------------------------------------------------------------------
    # Patch PPOController.control at class level so we record every invocation
    # (GPPPOController calls super().control(t) which dispatches to this).
    # Record: (applied_delta) = cores_after_ppo - cores_before_ppo per tick.
    # -------------------------------------------------------------------
    tick_records: list[tuple[float, float, int, float]] = []  # (before, after, a_idx, delta)
    ppo_original = PPOController.control

    def _recording_ppo(self_inner, t):
        before = self_inner.cores
        ppo_original(self_inner, t)
        after = self_inner.cores
        idx = self_inner.prev_act  # action index just stored by PPOController.control line 103
        applied_delta = after - before
        tick_records.append((before, after, idx, applied_delta))

    PPOController.control = _recording_ppo

    try:
        n_ticks = 50
        for tick in range(n_ticks):
            ctrl.control(float(tick))
    finally:
        PPOController.control = ppo_original  # always restore

    # -------------------------------------------------------------------
    # Inspect gp_data_buffer
    # -------------------------------------------------------------------
    buffer = list(ctrl.gp_data_buffer)
    assert len(buffer) > 0, (
        "gp_data_buffer should have entries after 50 ticks with pi_start_time=2 "
        "and gp_train_start=2"
    )

    observed_dim0_values = [entry[0][0] for entry in buffer]

    # CHECK 1: Domain exclusion — values 3 and 4 must never appear
    # (they are valid indices but impossible as deltas from {-2..+2})
    invalid_index_values = [v for v in observed_dim0_values if v in (3, 4)]
    assert len(invalid_index_values) == 0, (
        f"GP input dim 0 contains action-index values {{3,4}} which are impossible "
        f"delta-cores. Found: {invalid_index_values}. This means prev_action_ppo "
        f"stores the action index (0..4), not the delta cores (-2..+2)."
    )

    # CHECK 2: At least one negative value must appear
    # (action indices are always >= 0; deltas include -2 and -1)
    negative_values = [v for v in observed_dim0_values if v < 0]
    assert len(negative_values) > 0, (
        f"GP input dim 0 never contains a negative value across {len(buffer)} buffer "
        f"entries. All observed values: {sorted(set(float(v) for v in observed_dim0_values))}. "
        f"Deltas from {{-2..+2}} should include negatives. "
        f"This suggests the index (always >= 0) is stored instead of the delta."
    )

    # CHECK 3: Equivalence — every dim0 value must be a delta that PPO actually produced
    actual_deltas_produced = set(round(r[3]) for r in tick_records)
    for v in observed_dim0_values:
        assert round(float(v)) in actual_deltas_produced, (
            f"GP buffer dim 0 value {v} is not among the deltas actually applied "
            f"by PPO: {actual_deltas_produced}. "
            f"Action indices observed: {sorted(set(r[2] for r in tick_records))}. "
            f"This confirms the buffer stores the action index rather than the delta."
        )
