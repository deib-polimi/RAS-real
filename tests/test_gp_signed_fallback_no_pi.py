"""Tests for three connected fixes in `signed_shortfall` mode.

F4-b base: when buffer < gp_min_samples in signed_shortfall mode, the
fallback MUST produce comp=0 and source="None". Currently it produces
source="PI" (wrong).

Distrust-path twin: same fix must apply in the outcome-distrust branch.

Bug #6: is_gp_trained must also require self.gpr is not None. Currently
a full buffer with gpr=None causes an AttributeError inside _get_gp_prediction
(silently returns 0.0) and logs "Predicting GP..." misleadingly.

T1, T3: expected to FAIL pre-fix (current code prints "(PI)" not "(None)").
T2, T4: regression guards — legacy "sla_shortfall" must still use PI
        (expected to PASS pre-fix; document in report).
T5: expected to FAIL pre-fix (current code enters GP predict branch despite gpr=None).
"""
from __future__ import annotations

import re
from collections import deque
from unittest.mock import MagicMock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def controller_factory():
    pytest.importorskip("torch")
    from controllers.gpppo_controller import GPPPOController

    def _make(**overrides):
        params = dict(
            period=1, init_cores=4, min_cores=1.0, max_cores=16,
            st=1.0, st_max=1.0, min_st=1.0,
            train=False, deterministic_eval=True,
            burst_mode="none", trend_features=False,
            enable_log=False, log_dir="/tmp",
            bc=0.0, dc=0.0,
            pi_anti_windup=False, pi_e_clip=10.0,
            pi_error_form="linear", pi_rt_deadband_frac=0.30,
            gp_train_start=10, gp_min_samples=30, gp_train_freq=50,
            gp_max_buffer_size=500, pi_start_time=5,
            gp_time_period=200, gp_async=False,
            gp_target_mode="signed_shortfall", gp_normalize_inputs=True,
            gp_trust_mode="outcome", gp_distrust_dwell=0,
            gp_percentile=50, gp_lookahead_horizon=0,
            gp_adaptive_train=False,
            gp_drift_threshold=1.5, gp_min_train_interval=10,
            gp_eviction_keep=0,
        )
        params.update(overrides)
        ctrl = GPPPOController(**params)
        ctrl.setSLA(0.25)
        return ctrl

    return _make


class _FixedMonitoring:
    """Minimal Monitoring stub that returns constant values."""
    def __init__(self, rt=0.07, p95=0.07, q=0, r=10, u=10):
        self._rt = rt
        self._p95 = p95
        self._q = q
        self._r = r
        self._u = u

    def getRT(self):
        return self._rt

    def getRTp95(self):
        return self._p95

    def getQueueLen(self):
        return self._q

    def getArrivalRate(self):
        return self._r

    def getUsers(self):
        return self._u

    def tick(self, *a, **kw):
        pass


def _attach_monitoring(ctrl, **kw):
    """Attach a FixedMonitoring and prime the prev_* attributes so control()
    does not crash on first call."""
    ctrl.setMonitoring(_FixedMonitoring(**kw))
    ctrl.prev_act = 2          # action index 2 → delta 0 in [-2,-1,0,1,2]
    ctrl.prev_action_ppo = 0   # delta cores
    ctrl.prev_users = 10
    ctrl.prev_rt = 0.07


# ---------------------------------------------------------------------------
# T1 — signed_shortfall + buffer below min → comp=0, source=None
# ---------------------------------------------------------------------------

def test_signed_mode_fallback_when_buffer_below_min_uses_zero_comp(
    controller_factory, capsys
):
    """Invariant: in signed_shortfall mode, when the GP data buffer has fewer
    than gp_min_samples entries, the guardrail must contribute ZERO compensation
    and report source 'None'. The PI must NOT be used as a fallback substitute.
    """
    ctrl = controller_factory(gp_target_mode="signed_shortfall")
    _attach_monitoring(ctrl)

    # Buffer is empty → len < gp_min_samples=30 → should use comp=0, not PI
    assert len(ctrl.gp_data_buffer) == 0

    ctrl.control(t=10.0)

    out = capsys.readouterr().out
    # The printed summary line format: "Comp: X.XX -> Guardrail: Y.YY (Source)"
    assert re.search(r"Guardrail: 0\.00 \(None\)", out), (
        f"Expected 'Guardrail: 0.00 (None)' in output but got:\n{out}"
    )


# ---------------------------------------------------------------------------
# T2 — regression: legacy sla_shortfall mode still uses PI when buffer < min
# ---------------------------------------------------------------------------

def test_legacy_sla_shortfall_mode_fallback_still_uses_pi(
    controller_factory, capsys
):
    """Invariant (regression guard): legacy sla_shortfall mode must keep using
    PI as fallback when buffer is below gp_min_samples. Signed-mode fix must
    not break this path.
    """
    ctrl = controller_factory(gp_target_mode="sla_shortfall")
    _attach_monitoring(ctrl)

    assert len(ctrl.gp_data_buffer) == 0

    ctrl.control(t=10.0)

    out = capsys.readouterr().out
    assert re.search(r"\(PI\)", out), (
        f"Expected '(PI)' in output for legacy sla_shortfall fallback but got:\n{out}"
    )


# ---------------------------------------------------------------------------
# T3 — signed_shortfall + outcome distrust fires → comp=0, source=None
# ---------------------------------------------------------------------------

def test_signed_mode_distrust_path_uses_zero_comp(controller_factory, capsys):
    """Invariant: in signed_shortfall mode, when the outcome-based distrust
    branch fires (GP had been trusted but 95th-p violation exceeds threshold),
    the fallback compensation for that tick must be 0 with source 'None', not
    'PI'.
    """
    ctrl = controller_factory(
        gp_target_mode="signed_shortfall",
        gp_trust_mode="outcome",
        gp_distrust_dwell=0,
        gp_violation_threshold=0.0,  # any violation triggers distrust immediately
    )
    _attach_monitoring(ctrl)

    # Pre-fill buffer so is_gp_trained=True
    for _ in range(50):
        ctrl.gp_data_buffer.append((np.zeros(5), 0.0))

    # Provide a mock GPR so predict does not crash
    mock_gpr = MagicMock()
    mock_gpr.predict.return_value = (np.array([0.1]), np.array([0.01]))
    ctrl.gpr = mock_gpr
    ctrl._x_scaler = MagicMock()
    ctrl._x_scaler.transform.return_value = np.zeros((1, 5))

    # Fill performance_errors deque to capacity with values well above threshold
    # to guarantee the 95th-percentile check fires on first GP-trusted tick.
    max_len = ctrl.gp_performance_errors.maxlen
    for _ in range(max_len):
        ctrl.gp_performance_errors.append(1.0)  # SLA violation = 1.0 s >> threshold

    ctrl.is_gp_trusted = True
    ctrl.step_cnt = 1000  # ensure we are past gp_train_start

    ctrl.control(t=200.0)

    out = capsys.readouterr().out
    assert re.search(r"Guardrail: 0\.00 \(None\)", out), (
        f"Expected 'Guardrail: 0.00 (None)' after distrust in signed mode but got:\n{out}"
    )


# ---------------------------------------------------------------------------
# T4 — regression: legacy mode distrust path still uses PI
# ---------------------------------------------------------------------------

def test_legacy_mode_distrust_path_still_uses_pi(controller_factory, capsys):
    """Invariant (regression guard): in legacy sla_shortfall mode, the distrust
    fallback must keep producing source 'PI', not 'None'.
    """
    ctrl = controller_factory(
        gp_target_mode="sla_shortfall",
        gp_trust_mode="outcome",
        gp_distrust_dwell=0,
        gp_violation_threshold=0.0,
    )
    _attach_monitoring(ctrl)

    for _ in range(50):
        ctrl.gp_data_buffer.append((np.zeros(5), 0.0))

    mock_gpr = MagicMock()
    mock_gpr.predict.return_value = (np.array([0.1]), np.array([0.01]))
    ctrl.gpr = mock_gpr
    ctrl._x_scaler = MagicMock()
    ctrl._x_scaler.transform.return_value = np.zeros((1, 5))

    max_len = ctrl.gp_performance_errors.maxlen
    for _ in range(max_len):
        ctrl.gp_performance_errors.append(1.0)

    ctrl.is_gp_trusted = True
    ctrl.step_cnt = 1000

    ctrl.control(t=200.0)

    out = capsys.readouterr().out
    assert re.search(r"\(PI\)", out), (
        f"Expected '(PI)' after distrust in legacy mode but got:\n{out}"
    )


# ---------------------------------------------------------------------------
# T5 — Bug #6: is_gp_trained must require gpr is not None
# ---------------------------------------------------------------------------

def test_is_gp_trained_requires_gpr_not_none(controller_factory, capsys):
    """Invariant (Bug #6): when the GP buffer is full (>= gp_min_samples) but
    gpr is None (e.g. after a GP-RESET before first retrain completes), the
    controller must NOT enter the GP predict branch. The log line
    'Predicting GP with N samples' must be absent, and no AttributeError must
    be raised.
    """
    ctrl = controller_factory(gp_target_mode="signed_shortfall")
    _attach_monitoring(ctrl)

    # Fill buffer past gp_min_samples so old code sets is_gp_trained=True
    for _ in range(50):
        ctrl.gp_data_buffer.append((np.zeros(5), 0.0))

    # Explicitly set gpr=None — simulates state after GP-RESET before retrain
    ctrl.gpr = None
    ctrl.is_gp_trusted = True
    ctrl.step_cnt = 1000

    # Must not raise; must not log "Predicting GP"
    ctrl.control(t=10.0)

    out = capsys.readouterr().out
    assert "Predicting GP" not in out, (
        f"'Predicting GP' must not appear when gpr is None, but got:\n{out}"
    )
