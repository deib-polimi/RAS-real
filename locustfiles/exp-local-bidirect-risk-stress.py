"""Adaptive Safety Envelope (risk_violation mode) — STRESS regime.

Goal: prove the GP classifier ACTUALLY learns and intervenes (branches
≠ {None}) when the regime forces SLA violations. Pre-drift ρ≈0.88 with
occasional violations → multi-class buffer → GPC trains successfully.
Post-drift ρ≈1.32 → systematic violations → GP learns to VETO.

Pair with: exp-local-baseline-ppo-stress.py.

Calibration (rough estimate; full re-calib deferred to Phase B/C):
  payload=50000 → μ̂ ≈ 8.5 req/s/core (vs 17 at payload=25000)
  c_baseline at λ̂=60, μ̂=8.5, ρ_target=0.7:
    ⌈60/(8.5·0.7)⌉ = ⌈10.08⌉ = 11 → capped at max_cores=8
"""

CONFIG = {
    "hosts": ["http://localhost:8080", "http://localhost:8081"],
    "containerIds": ["graph_set", "graph_quota"],
    "request": {
        "method": "POST",
        "data": {"size": 50000},
        "headers": {"Content-Type": "application/json"},
        "path": "/",
    },
    "cpu_range_start": 0,
    "monitoring_window": 30,
    "app_sla": 0.25,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,

    "end": 600,

    "noise_start": 300,
    "noise_scale": 1.5,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 600,
    "noise_drift_period": 300,
    "seed": 42,

    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 60},
    },

    "controller": {
        "class": "GPPPOController",
        "params": {
            "period": 1,
            "init_cores": 6,
            "min_cores": 1.0,
            "max_cores": 8,
            "st": 1.0,
            "st_max": 1.0,
            "min_st": 1.0,
            "train": False,
            "deterministic_eval": True,
            "burst_mode": "none",
            "trend_features": False,
            "enable_log": True,
            "log_dir": "./logs",

            "bc": 0.0,
            "dc": 0.0,
            "pi_anti_windup": False,
            "pi_e_clip": 10.0,
            "pi_error_form": "linear",
            "pi_rt_deadband_frac": 0.30,

            "gp_train_start": 10,
            "gp_min_samples": 30,
            "gp_train_freq": 50,
            "gp_max_buffer_size": 500,
            "pi_start_time": 5,
            "gp_time_period": 200,
            "gp_async": True,

            # Step 1 v3: risk_violation mode
            "gp_target_mode": "risk_violation",
            "gp_normalize_inputs": True,
            "gp_trust_mode": "outcome",
            "gp_distrust_dwell": 0,

            "gp_lookahead_horizon": 0,
            "gp_adaptive_train": False,
            "gp_drift_threshold": 1.5,
            "gp_min_train_interval": 10,
            "gp_eviction_keep": 0,

            # H4 buffer reset at known drift onset
            "gp_buffer_reset_at": 300,

            # Step 1 v3 NEW knobs (μ̂=8.5 for payload=50K)
            "mu_estimate": 8.5,
            "rho_target": 0.7,
            "tau": 0.20,
            "kappa": 2.0,
            "alpha_clamp": 0.7,
            "dwell_ticks_min": 3,
            "dwell_ticks_max": 30,
            "floor_method": "utilization",
            "master_seed": 42,
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
