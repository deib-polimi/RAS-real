"""Tests for H4 — GP buffer reset knob (`gp_buffer_reset_at`).

Invariant: when `gp_buffer_reset_at` is set and the controller reaches that
timestamp for the first time, ALL GP-only state (buffer, model, scalers,
trust flags, in-flight training) is wiped, and the very next buffer write is
skipped.  PPO/PI state MUST remain untouched.

All five tests fail pre-implementation because:
  - `GPPPOController.__init__` does not accept `gp_buffer_reset_at`, and
  - `GPPPOController._maybe_reset_gp_state` does not exist.
"""
from __future__ import annotations

import time
from collections import deque
from unittest.mock import MagicMock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Fixtures
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
        # gp_buffer_reset_at intentionally NOT in defaults — overrides only,
        # so T4 (no-param test) exercises the default-None path.
        params.update(overrides)
        ctrl = GPPPOController(**params)
        ctrl.setSLA(0.25)
        return ctrl

    return _make


def _populate_buffer(ctrl, n=50):
    """Fill gp_data_buffer with n dummy (x, y) tuples."""
    for _ in range(n):
        ctrl.gp_data_buffer.append((np.zeros(5), 0.0))


# ---------------------------------------------------------------------------
# T1 — crossing the threshold clears GP state
# ---------------------------------------------------------------------------

def test_reset_clears_buffer_and_invalidates_model_when_t_crosses_threshold(
    controller_factory,
):
    """_maybe_reset_gp_state clears gp_data_buffer, gpr and _x_scaler
    when t first reaches gp_buffer_reset_at."""
    ctrl = controller_factory(gp_buffer_reset_at=300)
    _populate_buffer(ctrl, 50)
    ctrl.gpr = MagicMock()
    ctrl._x_scaler = MagicMock()

    # Before threshold: nothing changes
    ctrl._maybe_reset_gp_state(t=299.0)
    assert len(ctrl.gp_data_buffer) == 50
    assert ctrl.gpr is not None

    # At threshold: GP state wiped
    ctrl._maybe_reset_gp_state(t=300.0)
    assert len(ctrl.gp_data_buffer) == 0, (
        "gp_data_buffer must be empty after reset"
    )
    assert ctrl.gpr is None, "gpr must be None after reset"
    assert ctrl._x_scaler is None, "_x_scaler must be None after reset"


# ---------------------------------------------------------------------------
# T2 — idempotency: second call after reset does NOT clear re-populated buffer
# ---------------------------------------------------------------------------

def test_reset_is_idempotent_after_first_trigger(controller_factory):
    """_buffer_reset_done flag prevents a second reset from wiping the buffer
    that was rebuilt post-drift."""
    ctrl = controller_factory(gp_buffer_reset_at=300)
    _populate_buffer(ctrl, 50)
    ctrl.gpr = MagicMock()
    ctrl._x_scaler = MagicMock()

    ctrl._maybe_reset_gp_state(t=300.0)  # first reset
    assert len(ctrl.gp_data_buffer) == 0  # sanity — first reset worked

    # Simulate post-drift re-population
    _populate_buffer(ctrl, 5)

    # Second call at t > threshold: must NOT reset again
    ctrl._maybe_reset_gp_state(t=301.0)
    assert len(ctrl.gp_data_buffer) == 5, (
        "second call must not evict the post-reset buffer (idempotency)"
    )


# ---------------------------------------------------------------------------
# T3 — _skip_next_buffer_write is True immediately after reset
# ---------------------------------------------------------------------------

def test_first_buffer_write_after_reset_is_skipped(controller_factory):
    """After a GP buffer reset, _skip_next_buffer_write must be True so that
    the very next gp_data_buffer.append() in control() is skipped."""
    ctrl = controller_factory(gp_buffer_reset_at=300)
    _populate_buffer(ctrl, 10)
    ctrl._maybe_reset_gp_state(t=300.0)

    assert ctrl._skip_next_buffer_write is True, (
        "_skip_next_buffer_write must be True immediately after reset"
    )


# ---------------------------------------------------------------------------
# T4 — no reset when gp_buffer_reset_at is None (default)
# ---------------------------------------------------------------------------

def test_no_reset_when_param_is_none(controller_factory):
    """When gp_buffer_reset_at is not supplied (defaults to None),
    calling _maybe_reset_gp_state never clears the buffer."""
    ctrl = controller_factory()  # no gp_buffer_reset_at → default None
    _populate_buffer(ctrl, 50)
    gpr_original = ctrl.gpr

    ctrl._maybe_reset_gp_state(t=300.0)

    assert len(ctrl.gp_data_buffer) == 50, (
        "buffer must survive when gp_buffer_reset_at is None"
    )
    assert ctrl.gpr is gpr_original, "gpr must not change when knob is disabled"


# ---------------------------------------------------------------------------
# T5 — in-flight training process is terminated on reset
# ---------------------------------------------------------------------------

def test_reset_terminates_inflight_training_process(controller_factory):
    """When a GP training process is running at reset time, it must be
    terminated and all training-state attributes cleared."""
    ctrl = controller_factory(gp_buffer_reset_at=300)
    _populate_buffer(ctrl, 20)

    # Simulate an in-flight async training
    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    ctrl.gp_training_process = mock_proc
    ctrl.gp_training_in_progress = True
    ctrl.gp_training_start_time = time.time()
    ctrl._pending_model_path = "/tmp/fake-gp-model.pkl"

    ctrl._maybe_reset_gp_state(t=300.0)

    assert ctrl.gp_training_in_progress is False, (
        "gp_training_in_progress must be False after reset"
    )
    assert ctrl.gp_training_start_time is None, (
        "gp_training_start_time must be None after reset"
    )
    assert ctrl.gp_training_process is None, (
        "gp_training_process must be None after reset"
    )
    assert ctrl._pending_model_path is None, (
        "_pending_model_path must be None after reset"
    )
    # Verify termination was actually attempted on the mock process
    assert mock_proc.terminate.called, (
        "terminate() must have been called on the in-flight training process"
    )
