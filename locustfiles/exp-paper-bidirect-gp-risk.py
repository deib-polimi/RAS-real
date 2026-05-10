"""PPO + Adaptive Safety Envelope (Step 1 v3 — gp_target_mode="risk_violation").

NEW design replacing the buggy signed_shortfall mode (which caused +220% p95
RT degradation vs baseline on the AWS regime, see bidirect.log).

Architectural changes (Step 1 v3):
- GP is now a CLASSIFIER predicting P(RT_{t+1} > SLA | s, a) ∈ [0, 1]
  (vs old continuous signed shortfall regression)
- Decision tree VETO/CLAMP/COMPOSE with M/M/c safety floor
- Asymmetric safety: VETO branch always raises cores ≥ c_baseline
- Bumpless PI integral transfer across branches (S1.12)
- σ from predictive entropy of Bernoulli posterior (S1.16)
- Adaptive dwell hysteresis scaled by τ̂ (S1.18)

Pair with `exp-paper-baseline-ppo.py`. Same workload, drift, init/min/max cores.
Only the controller (and the new envelope) differs.

NOTE: μ̂=3.5 is calibrated rough estimate from historical AWS run (baseline.log
shows ~p95=440ms at c=8, suggesting μ_eff ~ 3.5-4.0 req/s/core in saturated
regime). Refine via `tools/calibrate_mu.py` if needed.
"""

CONFIG = {
    "hosts": ["http://localhost:8080", "http://localhost:8081"],
    "containerIds": ["graph_set", "graph_quota"],
    "request": {
        "method": "POST",
        "data": {"size": 25000},
        "headers": {"Content-Type": "application/json"},
        "path": "/function/graph_mst",
    },
    "cpu_range_start": 0,
    "monitoring_window": 30,
    "app_sla": 0.25,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,

    "end": 1200,

    # Drift: identical to original AWS regime (noise=1.3 step at t=300)
    "noise_start": 300,
    "noise_scale": 1.3,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 900,
    "noise_drift_period": 300,
    "seed": 42,

    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 40},
    },

    "controller": {
        "class": "GPPPOController",
        "params": {
            "period": 1,
            "init_cores": 4,
            "min_cores": 1.0,
            "max_cores": 16,
            "st": 1.0,
            "st_max": 1.0,
            "min_st": 1.0,
            "train": False,
            "deterministic_eval": True,
            "burst_mode": "none",
            "trend_features": False,
            "enable_log": True,
            "log_dir": "./logs",

            # PI muted (envelope drives via M/M/c floor + GP risk)
            "bc": 0.0,
            "dc": 0.0,
            "pi_anti_windup": False,
            "pi_e_clip": 10.0,
            "pi_error_form": "linear",
            "pi_rt_deadband_frac": 0.30,

            # GP scheduling
            "gp_train_start": 10,
            "gp_min_samples": 30,
            "gp_train_freq": 50,
            "gp_max_buffer_size": 500,
            "pi_start_time": 5,
            "gp_time_period": 200,
            "gp_async": True,

            # Step 1 v3: risk_violation (Bernoulli classifier) replacing signed_shortfall
            "gp_target_mode": "risk_violation",
            "gp_normalize_inputs": True,
            "gp_trust_mode": "outcome",
            "gp_distrust_dwell": 0,

            "gp_percentile": 50,            # legacy field, ignored in risk_violation
            "gp_lookahead_horizon": 0,
            "gp_adaptive_train": False,
            "gp_drift_threshold": 1.5,
            "gp_min_train_interval": 10,
            "gp_eviction_keep": 0,

            # H4: hard-reset GP at known drift onset
            "gp_buffer_reset_at": 300,

            # Step 1 v3 NEW knobs (risk_violation mode)
            "mu_estimate": 3.5,             # AWS estimate from baseline.log (rough)
            "rho_target": 0.95,             # relaxed → c_baseline ≈ ⌈40/(3.5·0.95)⌉ = 13
            "tau": 0.5,                     # FIX expert: was 0.20 → always-veto
            "kappa": 0.5,                   # FIX expert: was 2.0 → veto saturation
            "alpha_clamp": 0.7,             # CLAMP if RT > 0.7·SLA AND comp<0
            "dwell_ticks_min": 3,
            "dwell_ticks_max": 30,
            "floor_method": "utilization",
            "master_seed": 42,              # paired with baseline
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
