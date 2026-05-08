"""Tests for B1 — bidirectional GP guardrail (`gp_target_mode="signed_shortfall"`).

Architectural change: the GP is no longer monotone-up. With signed target,
the GP learns BOTH:
  - positive shortfall when RT > SLA (need more cores), and
  - negative shortfall when RT < SLA (excess cores, can downscale).
The clamp `max(0, comp)` in `control()` is removed in signed mode so the
final cores can DECREASE below `ppo_cores` (PPO's choice).

Tests verify the contract change. They skip locally without torch and run
on AWS where the controller stack is fully available.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# -----------------------------------------------------------------------------
# Fixtures — instantiate a minimal GPPPOController via importorskip
# -----------------------------------------------------------------------------

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
            gp_target_mode="sla_shortfall", gp_normalize_inputs=True,
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


# -----------------------------------------------------------------------------
# Target computation — signed mode produces SIGNED targets
# -----------------------------------------------------------------------------

def test_signed_shortfall_target_negative_when_rt_below_sla(controller_factory):
    """B1: with signed_shortfall, target < 0 when RT < SLA (excess capacity)."""
    ctrl = controller_factory(gp_target_mode="signed_shortfall")
    # Simulate the immediate-target write path
    ppo_cores = 8.0
    sla = 0.25
    rt_below_sla = 0.10  # well below SLA
    expected = ppo_cores * (rt_below_sla - sla) / sla  # = 8 · (-0.6) = -4.8
    target = ctrl._compute_gp_target(ppo_cores=ppo_cores, current_rt=rt_below_sla,
                                     pi_compensation=0.0)
    assert target == pytest.approx(expected), \
        f"signed target should be negative when RT<SLA, got {target}"
    assert target < 0


def test_signed_shortfall_target_positive_when_rt_above_sla(controller_factory):
    """B1: target > 0 when RT > SLA (need more cores) — same as legacy mode."""
    ctrl = controller_factory(gp_target_mode="signed_shortfall")
    ppo_cores = 8.0
    sla = 0.25
    rt_above_sla = 0.50
    expected = ppo_cores * (rt_above_sla - sla) / sla  # = 8 · 1.0 = 8.0
    target = ctrl._compute_gp_target(ppo_cores=ppo_cores, current_rt=rt_above_sla,
                                     pi_compensation=0.0)
    assert target == pytest.approx(expected)
    assert target > 0


def test_signed_shortfall_target_zero_when_rt_equals_sla(controller_factory):
    ctrl = controller_factory(gp_target_mode="signed_shortfall")
    target = ctrl._compute_gp_target(ppo_cores=8.0, current_rt=0.25,
                                     pi_compensation=0.0)
    assert target == pytest.approx(0.0)


def test_legacy_sla_shortfall_target_clamped_to_zero_below_sla(controller_factory):
    """Regression: legacy sla_shortfall mode still clamps to 0 when RT < SLA."""
    ctrl = controller_factory(gp_target_mode="sla_shortfall")
    target = ctrl._compute_gp_target(ppo_cores=8.0, current_rt=0.10,
                                     pi_compensation=0.0)
    assert target == 0.0  # clamped (legacy contract preserved)


def test_legacy_pi_compensation_target_unchanged(controller_factory):
    """Regression: pi_compensation mode just returns the PI delta."""
    ctrl = controller_factory(gp_target_mode="pi_compensation")
    target = ctrl._compute_gp_target(ppo_cores=8.0, current_rt=0.10,
                                     pi_compensation=2.5)
    assert target == 2.5


# -----------------------------------------------------------------------------
# Guardrail compensation — signed mode allows DOWNWARD correction
# -----------------------------------------------------------------------------

def test_guardrail_in_signed_mode_passes_negative_compensation(controller_factory):
    """B1: in signed mode, negative GP comp is NOT clamped to 0.
    The final cores can be below ppo_cores."""
    ctrl = controller_factory(gp_target_mode="signed_shortfall")
    final = ctrl._apply_guardrail(ppo_cores=10.0, actual_compensation=-3.0)
    assert final == pytest.approx(7.0), \
        f"signed mode should allow downscale: 10 + (-3) = 7, got {final}"


def test_guardrail_in_signed_mode_respects_min_cores_clip(controller_factory):
    """B1: even with huge negative comp, final >= min_cores (safety bound)."""
    ctrl = controller_factory(gp_target_mode="signed_shortfall", min_cores=2.0)
    final = ctrl._apply_guardrail(ppo_cores=4.0, actual_compensation=-100.0)
    assert final == 2.0  # clipped to min_cores


def test_guardrail_in_signed_mode_respects_max_cores_clip(controller_factory):
    """B1: huge positive comp → clipped to max_cores."""
    ctrl = controller_factory(gp_target_mode="signed_shortfall", max_cores=16)
    final = ctrl._apply_guardrail(ppo_cores=10.0, actual_compensation=+100.0)
    assert final == 16.0


def test_guardrail_in_legacy_mode_clamps_negative_to_zero(controller_factory):
    """Regression: legacy mode keeps the monotone-up clamp (max(0, comp))."""
    ctrl = controller_factory(gp_target_mode="sla_shortfall")
    final = ctrl._apply_guardrail(ppo_cores=10.0, actual_compensation=-5.0)
    assert final == pytest.approx(10.0), \
        f"legacy mode must NOT downscale: max(0,-5)=0 → final=10, got {final}"


def test_guardrail_in_legacy_mode_passes_positive_compensation(controller_factory):
    """Regression: legacy mode upscales as before."""
    ctrl = controller_factory(gp_target_mode="sla_shortfall")
    final = ctrl._apply_guardrail(ppo_cores=10.0, actual_compensation=+3.0)
    assert final == pytest.approx(13.0)


# -----------------------------------------------------------------------------
# Lookahead horizon — explicitly disabled for signed mode
# -----------------------------------------------------------------------------

def test_lookahead_horizon_disabled_in_signed_mode(controller_factory):
    """For now, lookahead is only supported with sla_shortfall.
    In signed mode we use the immediate (H=0) target path."""
    ctrl = controller_factory(gp_target_mode="signed_shortfall",
                              gp_lookahead_horizon=5)
    # The pending-buffer logic should NOT be activated for signed mode.
    # We assert this indirectly: _gp_pending stays empty after a buffer write.
    assert ctrl._uses_lookahead_path() is False
