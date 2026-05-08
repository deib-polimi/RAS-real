"""Factories for the 4 architectures + PPOPIController wrapper.

A1 — PPOController alone (current code).
A2 — CTControllerScaleX alone (PI on inverse-RT error).
A3 — PPO + PI always-on, additive monotone composition (no GP gate).
A4 — GPPPOController (current code, with all bugs A1..A4 / B1..B6 intact).
"""
from __future__ import annotations

import os
import sys

# Ensure repo root is importable so `controllers` package resolves
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from controllers.controller import Controller
from controllers.controltheoretical import CTControllerScaleX
from controllers.ppocontroller import PPOController
from controllers.gpppo_controller import GPPPOController


# ---------------------------------------------------------------------------
# A3 — PPO + PI wrapper (no GP)
# ---------------------------------------------------------------------------

class PPOPIController(Controller):
    """PPO + PI always-on additive composition.

    Each tick:
      1) PPO computes `ppo_cores` (its own decision).
      2) PI re-evaluates starting from `ppo_cores`, returns `pi_advice`.
      3) `final = ppo_cores + max(0, pi_advice − ppo_cores)`  (monotone-additive).
    """

    def __init__(self, period, init_cores, *, min_cores=1, max_cores=20,
                 st=0.8, train=True, BC=5.0, DC=10.0,
                 enable_log=False, log_dir="./logs"):
        super().__init__(period=period, init_cores=init_cores,
                         min_cores=min_cores, max_cores=max_cores, st=st)
        self.ppo = PPOController(
            period=period, init_cores=init_cores,
            min_cores=min_cores, max_cores=max_cores, st=st,
            train=train, enable_log=enable_log, log_dir=log_dir,
        )
        self.pi = CTControllerScaleX(
            period=period, init_cores=init_cores, min_cores=min_cores,
            max_cores=max_cores, BC=BC, DC=DC, st=st,
        )
        self.cores = init_cores

    def setMonitoring(self, monitoring):
        self.monitoring = monitoring
        self.ppo.setMonitoring(monitoring)
        self.pi.setMonitoring(monitoring)

    def setSLA(self, sla):
        self.sla = sla
        self.setpoint = sla * self.st
        self.ppo.setSLA(sla)
        self.pi.setSLA(sla)

    def control(self, t):
        # 1. PPO acts on shared `cores`
        self.ppo.cores = self.cores
        self.ppo.control(t)
        ppo_cores = self.ppo.cores
        # 2. PI advises starting from PPO's choice
        self.pi.cores = ppo_cores
        self.pi.control(t)
        pi_advice = self.pi.cores
        # 3. Monotone-additive composition
        comp = max(0.0, pi_advice - ppo_cores)
        self.cores = float(min(self.max_cores, max(self.min_cores, ppo_cores + comp)))


# ---------------------------------------------------------------------------
# Factories — each receives a `common` dict of shared kwargs
# ---------------------------------------------------------------------------

def make_a1_ppo(common):
    return PPOController(
        period=common["period"], init_cores=common["init_cores"],
        min_cores=common["min_cores"], max_cores=common["max_cores"],
        st=common["st"], train=common["train"], enable_log=False,
    )


def make_a1_ppo_argmax(common):
    """A1 with deterministic argmax action selection (mock RL-R3 fix)."""
    return PPOController(
        period=common["period"], init_cores=common["init_cores"],
        min_cores=common["min_cores"], max_cores=common["max_cores"],
        st=common["st"], train=common["train"], enable_log=False,
        deterministic_eval=True,
    )


def make_a2_pi(common):
    return CTControllerScaleX(
        period=common["period"], init_cores=common["init_cores"],
        min_cores=common["min_cores"], max_cores=common["max_cores"],
        BC=common.get("BC", 5.0), DC=common.get("DC", 10.0), st=common["st"],
    )


def make_a2_pi_aw(common):
    """A2 with anti-windup PI (CT-R2 mock + e-clipping)."""
    return CTControllerScaleX(
        period=common["period"], init_cores=common["init_cores"],
        min_cores=common["min_cores"], max_cores=common["max_cores"],
        BC=common.get("BC", 5.0), DC=common.get("DC", 10.0), st=common["st"],
        anti_windup=True, e_clip=10.0,
    )


def make_a3_ppopi(common):
    return PPOPIController(
        period=common["period"], init_cores=common["init_cores"],
        min_cores=common["min_cores"], max_cores=common["max_cores"],
        st=common["st"], train=common["train"],
        BC=common.get("BC", 5.0), DC=common.get("DC", 10.0),
        enable_log=False,
    )


def make_a3_ppopi_aw(common):
    """A3 with anti-windup PI + deterministic PPO eval (fair vs A1_ppo_argmax)."""
    ctrl = PPOPIController(
        period=common["period"], init_cores=common["init_cores"],
        min_cores=common["min_cores"], max_cores=common["max_cores"],
        st=common["st"], train=common["train"],
        BC=common.get("BC", 5.0), DC=common.get("DC", 10.0),
        enable_log=False,
    )
    ctrl.pi.anti_windup = common.get("anti_windup", True)
    ctrl.pi.e_clip = common.get("e_clip", 10.0)
    ctrl.pi.error_form = common.get("error_form", "inverse")
    ctrl.pi.rt_deadband_frac = common.get("rt_deadband_frac", 0.0)
    ctrl.ppo.deterministic_eval = True   # match A1_ppo_argmax for fairness
    return ctrl


def _make_a4(common, *, gp_target_mode, gp_normalize_inputs=False,
             gp_trust_mode="outcome", gp_distrust_dwell=0,
             gp_percentile=95, pi_anti_windup=False,
             gp_lookahead_horizon=0,
             gp_adaptive_train=False, gp_drift_threshold=1.5,
             gp_min_train_interval=10, gp_eviction_keep=0):
    """Build GPPPO with all knobs propagated via constructor (cloud config.json-ready)."""
    return GPPPOController(
        period=common["period"], init_cores=common["init_cores"],
        min_cores=common["min_cores"], max_cores=common["max_cores"],
        st=common["st"], train=common["train"],
        bc=common.get("BC", 5.0), dc=common.get("DC", 10.0),
        gp_min_samples=common.get("gp_min_samples", 30),
        gp_train_start=common.get("gp_train_start", 10),
        pi_start_time=common.get("pi_start_time", 5),
        gp_train_freq=common.get("gp_train_freq", 50),
        gp_max_buffer_size=common.get("gp_max_buffer_size", 500),
        gp_percentile=common.get("gp_percentile", gp_percentile),
        gp_target_mode=gp_target_mode,
        gp_normalize_inputs=gp_normalize_inputs,
        gp_trust_mode=gp_trust_mode,
        gp_distrust_dwell=gp_distrust_dwell,
        gp_lookahead_horizon=common.get("gp_lookahead_horizon", gp_lookahead_horizon),
        gp_adaptive_train=common.get("gp_adaptive_train", gp_adaptive_train),
        gp_drift_threshold=common.get("gp_drift_threshold", gp_drift_threshold),
        gp_min_train_interval=common.get("gp_min_train_interval", gp_min_train_interval),
        gp_eviction_keep=common.get("gp_eviction_keep", gp_eviction_keep),
        # Aux PI configuration — propagated via constructor (no post-set hack)
        pi_anti_windup=pi_anti_windup,
        pi_e_clip=common.get("e_clip", 10.0) if pi_anti_windup else None,
        pi_error_form=common.get("error_form", "inverse"),
        pi_rt_deadband_frac=common.get("rt_deadband_frac", 0.0),
        gp_async=False,  # synchronous training: simulator runs faster than mp.Process spawn
        enable_log=False,
    )


def make_a4_gpppo(common):
    """v1: current buggy code — GP target = PI compensation, no input normalization."""
    return _make_a4(common, gp_target_mode="pi_compensation",
                    gp_normalize_inputs=False)


def make_a4_gpppo_v2(common):
    """v2: + GP-R2 mock — target = SLA-shortfall counterfactual (cores deficit)."""
    return _make_a4(common, gp_target_mode="sla_shortfall",
                    gp_normalize_inputs=False)


def make_a4_gpppo_v3(common):
    """v3: v2 + GP-R1 mock — StandardScaler on GP inputs (ARD identifiability)."""
    return _make_a4(common, gp_target_mode="sla_shortfall",
                    gp_normalize_inputs=True)


def make_a4_gpppo_v4(common):
    """v4: v3 + SAFE-R3 mock — calibration-based trust gate (posterior σ check)."""
    return _make_a4(common, gp_target_mode="sla_shortfall",
                    gp_normalize_inputs=True,
                    gp_trust_mode="calibration")


def make_a4_gpppo_v5(common):
    """v5: v4 + SAFE-R1 mock — dwell-time on distrust (no immediate re-trust, fixes B2)."""
    return _make_a4(common, gp_target_mode="sla_shortfall",
                    gp_normalize_inputs=True,
                    gp_trust_mode="calibration",
                    gp_distrust_dwell=common.get("gp_distrust_dwell", 30))


def make_a4_gpppo_v6(common):
    """v6: v5 + GP percentile = 50 (mean of posterior, no UCB bias) + anti-windup PI."""
    return _make_a4(common, gp_target_mode="sla_shortfall",
                    gp_normalize_inputs=True,
                    gp_trust_mode="calibration",
                    gp_distrust_dwell=common.get("gp_distrust_dwell", 30),
                    gp_percentile=50,
                    pi_anti_windup=True)


def make_a4_gpppo_final(common):
    """OURS — fair-comparison version of GPPPO for headline table.

    Same anti-windup PI as A3_ppopi_aw baseline (so PI subsystems are identical),
    plus the single GP architectural fix (GP-R2: target = SLA shortfall counterfactual,
    not PI compensation). PPO uses argmax (matches A1_ppo_argmax for fairness).
    """
    ctrl = _make_a4(common, gp_target_mode="sla_shortfall", pi_anti_windup=True)
    ctrl.deterministic_eval = True   # match A1_ppo_argmax (PPO inside GPPPO uses argmax)
    return ctrl


ARCHITECTURES = {
    "A1_ppo":          ("PPO solo (frozen, sampled action)",            make_a1_ppo),
    "A1_ppo_argmax":   ("PPO solo (frozen, argmax — RL-R3)",            make_a1_ppo_argmax),
    "A2_pi":           ("PI solo (CTControllerScaleX)",                 make_a2_pi),
    "A2_pi_aw":        ("PI solo + anti-windup (CT-R2)",                make_a2_pi_aw),
    "A3_ppopi":        ("PPO+PI always-on (no GP)",                     make_a3_ppopi),
    "A3_ppopi_aw":     ("PPO+PI always-on + anti-windup PI",            make_a3_ppopi_aw),
    "A4_gpppo":        ("v1: current buggy",                            make_a4_gpppo),
    "A4_gpppo_v2":     ("v2: +GP-R2 (target=sla_shortfall)",            make_a4_gpppo_v2),
    "A4_gpppo_v3":     ("v3: +GP-R1 (norm)",                            make_a4_gpppo_v3),
    "A4_gpppo_v4":     ("v4: +SAFE-R3 (cal-trust)",                     make_a4_gpppo_v4),
    "A4_gpppo_v5":     ("v5: +SAFE-R1 (dwell)",                         make_a4_gpppo_v5),
    "A4_gpppo_v6":     ("v6: +CT-R2 (anti-windup) + GP mean percentile", make_a4_gpppo_v6),
    "A4_gpppo_final":  ("OURS — GP-R2 + anti-windup PI (fair vs A3_aw)", make_a4_gpppo_final),
}
