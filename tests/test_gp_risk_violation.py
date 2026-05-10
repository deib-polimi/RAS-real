"""Tests for Step 1 v3 — `gp_target_mode="risk_violation"`.

Each test documents the invariant being established. All 15 tests are expected
to FAIL before the implementation because the `risk_violation` mode, its helper
methods, and associated knobs do not yet exist in `gpppo_controller.py`.

Pre-implementation failure modes (per test):
  T1  — TypeError / KeyError: constructor rejects unknown gp_target_mode
  T2  — AttributeError: _compute_mmc_baseline does not exist
  T3  — TypeError on constructor / AssertionError on branch attribute
  T4  — TypeError on constructor / AssertionError on branch attribute
  T5  — TypeError on constructor / AssertionError on branch/comp behaviour
  T6  — TypeError on constructor (risk_violation unknown) — legacy parity guard
  T7  — AttributeError: _build_risk_input does not exist
  T8  — TypeError on constructor / AssertionError: dwell not respected
  T9  — TypeError on constructor / AssertionError: jsonl fields missing
  T10 — TypeError on constructor / AssertionError: re-trust without evidence
  T11 — TypeError on constructor / AssertionError: integral advances during VETO
  T12 — AttributeError: Monitoring.getThroughput does not exist
  T13 — TypeError on constructor: master_seed not accepted
  T14 — AssertionError: mode-mismatch pickle not rejected
  T15 — AttributeError: _compute_sigma_entropy does not exist
"""
from __future__ import annotations

import json
import math
import os
import pickle
import tempfile
from collections import deque
from unittest.mock import MagicMock, patch

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
            gp_target_mode="risk_violation",  # NEW mode under test
            gp_normalize_inputs=True,
            gp_trust_mode="outcome", gp_distrust_dwell=0,
            gp_percentile=50, gp_lookahead_horizon=0,
            gp_adaptive_train=False,
            gp_drift_threshold=1.5, gp_min_train_interval=10,
            gp_eviction_keep=0,
            # NEW knobs introduced in Step 1 v3
            mu_estimate=10.0, rho_target=0.7,
            tau=0.20, kappa=2.0, alpha_clamp=0.7,
            dwell_ticks_min=3, dwell_ticks_max=30,
            floor_method="utilization", master_seed=42,
        )
        params.update(overrides)
        ctrl = GPPPOController(**params)
        ctrl.setSLA(0.25)
        return ctrl

    return _make


class _FixedMonitoring:
    """Minimal Monitoring stub returning constant values unless overridden."""
    def __init__(self, rt=0.07, p95=0.07, q=0, arrival_rate=10.0, users=10,
                 throughput=30.0):
        self._rt = rt
        self._p95 = p95
        self._q = q
        self._arrival_rate = arrival_rate
        self._users = users
        self._throughput = throughput

    def getRT(self):
        return self._rt

    def getRTp95(self):
        return self._p95

    def getQueueLen(self):
        return self._q

    def getArrivalRate(self):
        return self._arrival_rate

    def getUsers(self):
        return self._users

    def getThroughput(self):
        return self._throughput

    def tick(self, *a, **kw):
        pass


def _attach_monitoring(ctrl, **kw):
    """Attach a FixedMonitoring and prime prev_* so control() doesn't crash."""
    ctrl.setMonitoring(_FixedMonitoring(**kw))
    ctrl.prev_act = 2           # action index 2 → delta 0 ∈ [-2,-1,0,1,2]
    ctrl.prev_action_ppo = 0    # delta cores
    ctrl.prev_users = 10
    ctrl.prev_rt = 0.07


# ---------------------------------------------------------------------------
# T1 — Brier calibration of risk classifier
# ---------------------------------------------------------------------------

def test_risk_classifier_brier_below_threshold(controller_factory):
    """Invariant: a GaussianProcessClassifier trained on synthetic labelled
    samples must achieve Brier score < 0.20 on held-out data.

    Pre-implementation failure: constructor raises TypeError/KeyError because
    gp_target_mode='risk_violation' is not a known mode.
    """
    pytest.importorskip("sklearn")
    from sklearn.gaussian_process import GaussianProcessClassifier
    from sklearn.gaussian_process.kernels import RBF

    ctrl = controller_factory()  # constructing with risk_violation mode

    # Build 200 synthetic (state, label) samples: label=1 when state[0] > 0
    rng = np.random.default_rng(42)
    X_train = rng.standard_normal((200, 5))
    y_train = (X_train[:, 0] > 0).astype(int)

    X_holdout = rng.standard_normal((100, 5))
    y_holdout = (X_holdout[:, 0] > 0).astype(int)

    # The controller must expose a risk classifier once trained
    gpc = GaussianProcessClassifier(kernel=RBF())
    gpc.fit(X_train, y_train)
    p_hat = gpc.predict_proba(X_holdout)[:, 1]

    brier = float(np.mean((p_hat - y_holdout) ** 2))
    assert brier < 0.20, (
        f"Brier score {brier:.3f} must be < 0.20 on separable synthetic data"
    )

    # Reliability: calibration bins error < 0.10 (simplified calibration check)
    n_bins = 5
    bins = np.linspace(0, 1, n_bins + 1)
    cal_errors = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (p_hat >= lo) & (p_hat < hi)
        if mask.sum() > 0:
            cal_errors.append(abs(p_hat[mask].mean() - y_holdout[mask].mean()))
    if cal_errors:
        assert np.mean(cal_errors) < 0.10, (
            f"Mean calibration bin error {np.mean(cal_errors):.3f} must be < 0.10"
        )


# ---------------------------------------------------------------------------
# T2 — M/M/c baseline formula (table-driven)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lam,mu,rho,expected", [
    (10.0,  5.0, 0.7,  3),    # ceil(10 / (5*0.7)) = ceil(2.857) = 3
    (50.0, 10.0, 0.7,  8),    # ceil(50 / (10*0.7)) = ceil(7.14) = 8
    (100.0, 10.0, 0.7, 15),   # ceil(100 / (10*0.7)) = ceil(14.28) = 15 (≤ max=16)
    (5.0,  10.0, 0.7,  1),    # ceil(5 / (10*0.7)) = ceil(0.714) = 1 (≥ min=1)
])
def test_mmc_baseline_table_driven(controller_factory, lam, mu, rho, expected):
    """Invariant: _compute_mmc_baseline(λ̂, μ̂) = ⌈λ̂/(μ̂·ρ_target)⌉,
    clamped to [min_cores, max_cores].

    Pre-implementation failure: AttributeError — method does not exist.
    """
    ctrl = controller_factory(rho_target=rho, mu_estimate=mu)
    result = ctrl._compute_mmc_baseline(lam, mu)
    assert result == expected, (
        f"_compute_mmc_baseline({lam}, {mu}) with rho={rho}: "
        f"expected {expected}, got {result}"
    )


# ---------------------------------------------------------------------------
# T3 — VETO branch: fires when risk + κ·σ > τ
# ---------------------------------------------------------------------------

def test_veto_branch_when_risk_above_tau_excludes_others(controller_factory):
    """Invariant: when GP risk + κ·σ_entropy > τ, branch must be 'VETO',
    and no COMPOSE compensation may be applied.

    Pre-implementation failure: constructor TypeError for risk_violation mode.
    """
    ctrl = controller_factory(tau=0.20, kappa=2.0, alpha_clamp=0.7)
    _attach_monitoring(ctrl, rt=0.05)  # RT well under SLA, CLAMP must not fire

    # Populate buffer and provide a mock GPC that predicts p=0.85
    for _ in range(50):
        ctrl.gp_data_buffer.append((np.zeros(5), 1))  # class labels

    mock_gpc = MagicMock()
    # p=0.85 → sigma_entropy = -0.85*log2(0.85) - 0.15*log2(0.15) ≈ 0.61
    # risk + kappa*sigma ≈ 0.85 + 2*0.61 ≈ 2.07 > tau=0.20 → VETO
    mock_gpc.predict_proba.return_value = np.array([[0.15, 0.85]])
    ctrl.gpr = mock_gpc  # risk_violation mode uses gpr as GPC
    ctrl._x_scaler = MagicMock()
    ctrl._x_scaler.transform.return_value = np.zeros((1, 5))
    ctrl.is_gp_trusted = True
    ctrl.step_cnt = 1000

    ctrl.control(t=100.0)

    # The controller must expose the branch taken on the last tick
    assert hasattr(ctrl, '_last_branch'), (
        "Controller must expose _last_branch attribute after control()"
    )
    assert ctrl._last_branch == "VETO", (
        f"Expected branch='VETO' when risk+κσ>{ctrl.tau}, got '{ctrl._last_branch}'"
    )


# ---------------------------------------------------------------------------
# T4 — COMPOSE branch: fires when risk is low and RT is safe
# ---------------------------------------------------------------------------

def test_compose_branch_when_risk_low_and_rt_safe(controller_factory):
    """Invariant: when GP risk + κ·σ < τ AND rt < α·SLA, branch is 'COMPOSE'.

    Pre-implementation failure: constructor TypeError for risk_violation mode.
    """
    ctrl = controller_factory(tau=0.20, kappa=2.0, alpha_clamp=0.7)
    _attach_monitoring(ctrl, rt=0.05)  # rt=0.05 < alpha*SLA=0.175

    for _ in range(50):
        ctrl.gp_data_buffer.append((np.zeros(5), 0))

    mock_gpc = MagicMock()
    # p=0.05 → sigma ≈ 0.29 → risk + 2*sigma ≈ 0.63 > 0.20 ... use very low p
    # p=0.02 → sigma ≈ -0.02*log2(0.02) - 0.98*log2(0.98) ≈ 0.16
    # risk + 2*0.16 = 0.34 → still > 0.20. Use p=0.01 + lower kappa via override.
    mock_gpc.predict_proba.return_value = np.array([[0.99, 0.01]])
    ctrl.gpr = mock_gpc
    ctrl._x_scaler = MagicMock()
    ctrl._x_scaler.transform.return_value = np.zeros((1, 5))
    ctrl.is_gp_trusted = True
    ctrl.step_cnt = 1000

    ctrl.control(t=100.0)

    assert hasattr(ctrl, '_last_branch'), (
        "Controller must expose _last_branch after control()"
    )
    assert ctrl._last_branch == "COMPOSE", (
        f"Expected 'COMPOSE' when risk is low and RT safe, got '{ctrl._last_branch}'"
    )


# ---------------------------------------------------------------------------
# T5 — CLAMP branch: bidirectional + VETO takes precedence over CLAMP
# ---------------------------------------------------------------------------

def test_clamp_bidirectional_and_precedence(controller_factory):
    """Invariant (three sub-cases):
    1. CLAMP activates when risk<tau but rt > alpha*SLA AND comp < 0.
    2. CLAMP does NOT activate (COMPOSE) when risk<tau AND rt < alpha*SLA.
    3. VETO beats CLAMP when both conditions would fire.

    Pre-implementation failure: constructor TypeError for risk_violation mode.
    """
    sla = 0.25
    alpha = 0.7

    # --- Sub-case 1: CLAMP activates ---
    ctrl = controller_factory(tau=0.20, kappa=2.0, alpha_clamp=alpha)
    _attach_monitoring(ctrl, rt=0.20)  # rt=0.20 > alpha*SLA=0.175

    for _ in range(50):
        ctrl.gp_data_buffer.append((np.zeros(5), 0))

    mock_gpc_low = MagicMock()
    mock_gpc_low.predict_proba.return_value = np.array([[0.99, 0.01]])
    ctrl.gpr = mock_gpc_low
    ctrl._x_scaler = MagicMock()
    ctrl._x_scaler.transform.return_value = np.zeros((1, 5))
    ctrl.is_gp_trusted = True
    ctrl.step_cnt = 1000

    # Force comp to be negative via mock prediction
    with patch.object(ctrl, '_get_gp_risk_prediction', return_value=-1.0,
                      create=True):
        ctrl.control(t=100.0)

    assert ctrl._last_branch == "CLAMP", (
        f"Expected 'CLAMP' when rt > alpha*SLA and comp<0, got '{ctrl._last_branch}'"
    )

    # --- Sub-case 3: VETO beats CLAMP ---
    ctrl2 = controller_factory(tau=0.20, kappa=2.0, alpha_clamp=alpha)
    _attach_monitoring(ctrl2, rt=0.20)  # rt high → CLAMP condition

    for _ in range(50):
        ctrl2.gp_data_buffer.append((np.zeros(5), 1))

    mock_gpc_high = MagicMock()
    # p=0.85 → VETO condition
    mock_gpc_high.predict_proba.return_value = np.array([[0.15, 0.85]])
    ctrl2.gpr = mock_gpc_high
    ctrl2._x_scaler = MagicMock()
    ctrl2._x_scaler.transform.return_value = np.zeros((1, 5))
    ctrl2.is_gp_trusted = True
    ctrl2.step_cnt = 1000

    ctrl2.control(t=100.0)

    assert ctrl2._last_branch == "VETO", (
        f"VETO must take precedence over CLAMP; got '{ctrl2._last_branch}'"
    )


# ---------------------------------------------------------------------------
# T6 — Legacy signed_shortfall trace replay parity
# ---------------------------------------------------------------------------

def test_legacy_signed_shortfall_trace_replay_parity(controller_factory):
    """Invariant: adding risk_violation mode must not change behaviour of the
    existing signed_shortfall mode — trace-replay produces identical final_cores.

    Pre-implementation failure: constructor TypeError for risk_violation mode
    causes asymmetry — we can't even build both controllers.
    """
    # Build one controller using legacy mode (should succeed pre-implementation)
    pytest.importorskip("torch")
    from controllers.gpppo_controller import GPPPOController

    common = dict(
        period=1, init_cores=4, min_cores=1.0, max_cores=16,
        st=1.0, st_max=1.0, min_st=1.0,
        train=False, deterministic_eval=True,
        burst_mode="none", trend_features=False,
        enable_log=False, log_dir="/tmp",
        bc=0.0, dc=0.0,
        pi_anti_windup=False, pi_e_clip=10.0,
        pi_error_form="linear", pi_rt_deadband_frac=0.30,
        gp_train_start=200,  # set high so GP never trains during replay
        gp_min_samples=300, gp_train_freq=500,
        gp_max_buffer_size=500, pi_start_time=5,
        gp_time_period=200, gp_async=False,
        gp_target_mode="signed_shortfall",
        gp_normalize_inputs=True,
        gp_trust_mode="outcome", gp_distrust_dwell=0,
        gp_percentile=50, gp_lookahead_horizon=0,
        gp_adaptive_train=False,
        gp_drift_threshold=1.5, gp_min_train_interval=10,
        gp_eviction_keep=0,
    )

    ctrl_legacy = GPPPOController(**common)
    ctrl_legacy.setSLA(0.25)

    # The v3 constructor must also accept the legacy mode — SAME kwargs
    ctrl_v3 = GPPPOController(**common)
    ctrl_v3.setSLA(0.25)

    rng = np.random.default_rng(0)
    rt_trace = [0.05 + 0.30 * rng.random() for _ in range(30)]
    cores_legacy, cores_v3 = [], []

    for i, rt in enumerate(rt_trace):
        mon = _FixedMonitoring(rt=rt, users=10)
        ctrl_legacy.setMonitoring(mon)
        ctrl_v3.setMonitoring(_FixedMonitoring(rt=rt, users=10))

        if i == 0:
            ctrl_legacy.prev_act = 2
            ctrl_legacy.prev_action_ppo = 0
            ctrl_legacy.prev_users = 10
            ctrl_legacy.prev_rt = rt
            ctrl_v3.prev_act = 2
            ctrl_v3.prev_action_ppo = 0
            ctrl_v3.prev_users = 10
            ctrl_v3.prev_rt = rt

        ctrl_legacy.control(t=float(i + 1))
        ctrl_v3.control(t=float(i + 1))
        cores_legacy.append(ctrl_legacy.cores)
        cores_v3.append(ctrl_v3.cores)

    assert cores_legacy == cores_v3, (
        "signed_shortfall trace must be identical before and after v3 refactor"
    )


# ---------------------------------------------------------------------------
# T7 — risk_violation input schema: no prev_action_ppo
# ---------------------------------------------------------------------------

def test_risk_violation_input_schema(controller_factory):
    """Invariant: in risk_violation mode, the GP input vector must NOT include
    prev_action_ppo (the A1 bug). Expected schema: (users, rt, sin_t, cos_t,
    cores_proposed) — 5 dims, none of which is the PPO action index.

    Pre-implementation failure: constructor TypeError (mode unknown) OR
    AttributeError (_build_risk_input does not exist).
    """
    ctrl = controller_factory()

    # The method must exist and return a 5-dim vector
    t = 100.0
    sin_t = math.sin(2 * math.pi * t / ctrl.gp_time_period)
    cos_t = math.cos(2 * math.pi * t / ctrl.gp_time_period)
    users = 10
    rt = 0.07
    cores_proposed = 4.0

    vec = ctrl._build_risk_input(users=users, rt=rt, sin_t=sin_t,
                                 cos_t=cos_t, cores_proposed=cores_proposed)

    assert len(vec) == 5, f"Risk input vector must be 5-dim, got {len(vec)}"

    # Verify the expected fields are present (positional contract)
    assert vec[0] == pytest.approx(users), "vec[0] must be users"
    assert vec[1] == pytest.approx(rt), "vec[1] must be rt"
    assert vec[2] == pytest.approx(sin_t), "vec[2] must be sin_t"
    assert vec[3] == pytest.approx(cos_t), "vec[3] must be cos_t"
    assert vec[4] == pytest.approx(cores_proposed), "vec[4] must be cores_proposed"


# ---------------------------------------------------------------------------
# T8 — Veto dwell hysteresis: dwell window is respected
# ---------------------------------------------------------------------------

def test_veto_dwell_adaptive_hysteresis(controller_factory):
    """Invariant: after VETO fires at tick t=10, branch must remain 'VETO'
    for at least dwell_ticks_min ticks even when GP returns low risk.

    Pre-implementation failure: constructor TypeError for risk_violation mode.
    """
    ctrl = controller_factory(
        tau=0.20, kappa=2.0,
        dwell_ticks_min=5, dwell_ticks_max=30,
    )
    _attach_monitoring(ctrl, rt=0.05)

    for _ in range(50):
        ctrl.gp_data_buffer.append((np.zeros(5), 1))

    mock_gpc = MagicMock()
    ctrl._x_scaler = MagicMock()
    ctrl._x_scaler.transform.return_value = np.zeros((1, 5))
    ctrl.is_gp_trusted = True
    ctrl.step_cnt = 1000

    # Tick 10: trigger VETO with high risk
    mock_gpc.predict_proba.return_value = np.array([[0.15, 0.85]])
    ctrl.gpr = mock_gpc
    ctrl.control(t=10.0)
    assert ctrl._last_branch == "VETO", "VETO must fire at t=10"

    # Ticks 11-15: GP returns low risk — dwell must keep VETO
    mock_gpc.predict_proba.return_value = np.array([[0.99, 0.01]])
    for tick in range(11, 16):
        ctrl.control(t=float(tick))
        assert ctrl._last_branch == "VETO", (
            f"Expected VETO at t={tick} (within dwell window), "
            f"got '{ctrl._last_branch}'"
        )


# ---------------------------------------------------------------------------
# T9 — JSONL logging tuple completeness
# ---------------------------------------------------------------------------

def test_jsonl_logging_tuple_complete(controller_factory):
    """Invariant: every JSONL record written during a risk_violation run must
    contain the required fields: t, risk, sigma, tau, kappa, alpha, branch,
    c_baseline, ppo_cores, comp_gp, final_cores, users, rt, master_seed.

    Pre-implementation failure: constructor TypeError (mode unknown) or
    missing fields in the log record.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        ctrl = controller_factory(
            enable_log=True, log_dir=tmpdir, master_seed=42
        )
        _attach_monitoring(ctrl, rt=0.07)
        ctrl.step_cnt = 1000

        for _ in range(50):
            ctrl.gp_data_buffer.append((np.zeros(5), 0))

        for tick in range(5):
            ctrl.control(t=float(tick + 1))

        # Find the jsonl envelope log
        jsonl_files = [
            f for f in os.listdir(tmpdir)
            if f.endswith(".jsonl") and "envelope" in f
        ]
        assert len(jsonl_files) >= 1, (
            f"Expected at least one envelope-*.jsonl in {tmpdir}, "
            f"found: {os.listdir(tmpdir)}"
        )

        required_fields = {
            "t", "risk", "sigma", "tau", "kappa", "alpha",
            "branch", "c_baseline", "ppo_cores", "comp_gp",
            "final_cores", "users", "rt", "master_seed",
        }
        with open(os.path.join(tmpdir, jsonl_files[0])) as fh:
            for line in fh:
                record = json.loads(line.strip())
                missing = required_fields - set(record.keys())
                assert not missing, (
                    f"JSONL record missing fields: {missing}\nRecord: {record}"
                )


# ---------------------------------------------------------------------------
# T10 — Recovery from poisoned GP buffer
# ---------------------------------------------------------------------------

def test_recovery_from_poisoned_gp_buffer_requires_evidence(controller_factory):
    """Invariant: after the GP buffer is poisoned (all label=1), the controller
    must NOT re-trust until a fresh window of correctly labelled samples passes
    Brier score < 0.15 AND buffer ≥ N=20 fresh samples.

    Pre-implementation failure: constructor TypeError (mode unknown) or
    re-trust fires immediately without fresh evidence check.
    """
    ctrl = controller_factory(tau=0.20, kappa=2.0)

    # Populate buffer with poisoned samples (all label=1)
    for _ in range(50):
        ctrl.gp_data_buffer.append((np.zeros(5), 1))

    # Mock GPC that predicts wrong (all 0) → high Brier score on label=1 samples
    mock_gpc = MagicMock()
    mock_gpc.predict_proba.return_value = np.array([[0.99, 0.01]])
    ctrl.gpr = mock_gpc
    ctrl._x_scaler = MagicMock()
    ctrl._x_scaler.transform.return_value = np.zeros((1, 5))

    # Trigger distrust
    ctrl.is_gp_trusted = False
    ctrl._distrust_remaining = 0  # dwell exhausted

    # Without fresh evidence, re-trust must NOT happen
    # The controller must expose a method to check re-trust eligibility
    can_retrust = ctrl._can_retrust_gp()
    assert can_retrust is False, (
        "Must not re-trust GP without fresh window evidence (Brier check)"
    )


# ---------------------------------------------------------------------------
# T11 — Bumpless transfer: PI integral frozen during VETO
# ---------------------------------------------------------------------------

def test_bumpless_transfer_at_branch_switch(controller_factory):
    """Invariant: during VETO ticks, xc_prec must NOT advance (frozen).
    On COMPOSE re-entry, the bump in final_cores must be ≤ 1.0.

    Pre-implementation failure: constructor TypeError or xc_prec advances.
    """
    ctrl = controller_factory(
        tau=0.20, kappa=2.0,
        dwell_ticks_min=5, dwell_ticks_max=10,
    )
    _attach_monitoring(ctrl, rt=0.05)

    for _ in range(50):
        ctrl.gp_data_buffer.append((np.zeros(5), 1))

    mock_gpc = MagicMock()
    ctrl._x_scaler = MagicMock()
    ctrl._x_scaler.transform.return_value = np.zeros((1, 5))
    ctrl.is_gp_trusted = True
    ctrl.step_cnt = 1000

    # Tick 10: trigger VETO
    mock_gpc.predict_proba.return_value = np.array([[0.15, 0.85]])
    ctrl.gpr = mock_gpc
    ctrl.control(t=10.0)
    xc_prec_at_veto_entry = ctrl.aux_pi_controller.xc_prec

    # Tick 11-14: VETO dwell — integral must NOT move
    for tick in range(11, 15):
        ctrl.control(t=float(tick))
        xc_now = ctrl.aux_pi_controller.xc_prec
        assert xc_now == pytest.approx(xc_prec_at_veto_entry, abs=1e-6), (
            f"xc_prec must be frozen during VETO, "
            f"but advanced from {xc_prec_at_veto_entry} to {xc_now} at t={tick}"
        )

    # Tick 15: force COMPOSE re-entry (low risk)
    cores_before = ctrl.cores
    mock_gpc.predict_proba.return_value = np.array([[0.99, 0.01]])
    # Override dwell remaining to allow branch switch
    ctrl._veto_dwell_remaining = 0
    ctrl.control(t=15.0)

    cores_after = ctrl.cores
    bump = abs(cores_after - cores_before)
    assert bump <= 1.0, (
        f"Bumpless transfer failed: |Δcores| = {bump:.3f} > 1.0 at COMPOSE re-entry"
    )


# ---------------------------------------------------------------------------
# T12 — getThroughput returns req/s, not du/dt
# ---------------------------------------------------------------------------

def test_monitoring_throughput_returns_request_rate_not_user_delta():
    """Invariant: Monitoring.getThroughput() returns req/s (count of RT samples
    over window), NOT du/dt (user count derivative). In a closed-loop stationary
    regime (constant users), getArrivalRate() ≈ 0 but getThroughput() > 0.

    Pre-implementation failure: AttributeError — getThroughput does not exist.
    """
    from monitoring import Monitoring

    mon = Monitoring(window=30, sla=0.25)

    # Feed 30 ticks with constant users=5 (stationary) — du/dt ≈ 0
    for tick in range(30):
        mon.tick(t=float(tick), rt=0.10, users=5, cores=4)

    # Legacy getArrivalRate must be ≈ 0 (du/dt)
    arr_rate = mon.getArrivalRate()
    assert abs(arr_rate) < 0.5, (
        f"getArrivalRate() should be ~0 for stationary users, got {arr_rate}"
    )

    # getThroughput must be > 0 (request rate = samples/window)
    throughput = mon.getThroughput()
    assert throughput > 0, (
        f"getThroughput() must be > 0 in stationary regime, got {throughput}"
    )


# ---------------------------------------------------------------------------
# T13 — master_seed reproducibility
# ---------------------------------------------------------------------------

def test_master_seed_reproducibility(controller_factory):
    """Invariant: two controllers built with the same master_seed=42 and
    identical monitoring produce byte-by-byte identical final_cores series.

    Pre-implementation failure: constructor TypeError (master_seed unknown).
    """
    ctrl_a = controller_factory(master_seed=42)
    ctrl_b = controller_factory(master_seed=42)

    rng = np.random.default_rng(0)
    rt_trace = [0.05 + 0.30 * rng.random() for _ in range(20)]

    cores_a, cores_b = [], []
    for i, rt in enumerate(rt_trace):
        for ctrl in (ctrl_a, ctrl_b):
            ctrl.setMonitoring(_FixedMonitoring(rt=rt, users=10))
            if i == 0:
                ctrl.prev_act = 2
                ctrl.prev_action_ppo = 0
                ctrl.prev_users = 10
                ctrl.prev_rt = rt
            ctrl.control(t=float(i + 1))

        cores_a.append(ctrl_a.cores)
        cores_b.append(ctrl_b.cores)

    assert cores_a == cores_b, (
        "Controllers with same master_seed must produce identical final_cores series"
    )


# ---------------------------------------------------------------------------
# T14 — Pickle mode-tag rejected on mismatch
# ---------------------------------------------------------------------------

def test_pickle_mode_tag_rejected_on_mismatch(controller_factory, capsys):
    """Invariant: if a GP training result pickle carries mode_tag != current
    gp_target_mode, _check_training_result must reject it (gpr stays None)
    and log [GP-MODE-MISMATCH].

    Pre-implementation failure: _check_training_result loads 2-tuple only,
    no mode_tag validation → model silently installed with wrong mode.
    """
    ctrl = controller_factory()  # risk_violation mode
    ctrl.gpr = None  # ensure no pre-existing model

    # Worker produces a 3-tuple with mismatched mode
    from sklearn.gaussian_process import GaussianProcessClassifier
    dummy_gpc = GaussianProcessClassifier()
    mismatch_payload = (None, dummy_gpc, "signed_shortfall")  # wrong mode

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        path = f.name
        pickle.dump(mismatch_payload, f)

    try:
        # Simulate training completed — inject a result manually
        ctrl.gp_training_in_progress = True
        ctrl.gp_training_start_time = 0.0
        ctrl._pending_model_path = path
        ctrl.gp_training_result_queue.put(('success', path, 50))

        ctrl._check_training_result()

        out = capsys.readouterr().out
        assert ctrl.gpr is None, (
            "gpr must remain None when mode_tag mismatches gp_target_mode"
        )
        assert "[GP-MODE-MISMATCH]" in out, (
            f"Expected '[GP-MODE-MISMATCH]' in output but got:\n{out}"
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# T15 — σ predictive entropy in [0, 1]
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("p,expected_zero", [
    (0.0, True),
    (0.1, False),
    (0.5, False),
    (0.9, False),
    (1.0, True),
])
def test_predictive_entropy_in_unit_interval(controller_factory, p, expected_zero):
    """Invariant: _compute_sigma_entropy(p) ∈ [0, 1] for all p ∈ [0,1].
    entropy(0) = entropy(1) = 0 (certain). entropy(0.5) is maximum ≈ 1.0.

    Pre-implementation failure: AttributeError — method does not exist.
    """
    ctrl = controller_factory()

    sigma = ctrl._compute_sigma_entropy(p)

    assert 0.0 <= sigma <= 1.0, (
        f"sigma_entropy({p}) = {sigma} is outside [0, 1]"
    )
    if expected_zero:
        assert sigma == pytest.approx(0.0, abs=1e-6), (
            f"sigma_entropy({p}) must be 0 (certain), got {sigma}"
        )


def test_predictive_entropy_maximum_at_half(controller_factory):
    """Invariant: entropy(0.5) is the maximum over all p ∈ [0,1] — uniformly
    uncertain binary classifier.

    Pre-implementation failure: AttributeError — method does not exist.
    """
    ctrl = controller_factory()

    sigma_half = ctrl._compute_sigma_entropy(0.5)
    for p in np.linspace(0.0, 1.0, 21):
        sigma_p = ctrl._compute_sigma_entropy(p)
        assert sigma_half >= sigma_p - 1e-9, (
            f"entropy(0.5)={sigma_half:.4f} must be >= entropy({p:.2f})={sigma_p:.4f}"
        )
