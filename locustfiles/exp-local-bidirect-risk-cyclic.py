"""Adaptive Safety Envelope — cyclic workload stress test.

Same workload as exp-local-baseline-ppo-cyclic.py but with risk_violation mode.
SinGen oscillates λ in [2, 42] over 600s period. End=1800s (3 cycles).
Drift @ t=750 (peak cycle 2) creates max stress for PPO. GP should learn the
oscillating pattern pre-drift (1.25 cycles), then re-adapt post-drift.

Hypothesis: GP envelope reduces violations during peaks (especially post-drift)
where PPO oscillates dangerously to low cores.
"""

CONFIG = {
    "hosts": ["http://localhost:8080", "http://localhost:8081"],
    "containerIds": ["graph_set", "graph_quota"],
    "request": {
        "method": "POST",
        "data": {"size": 80000},
        "headers": {"Content-Type": "application/json"},
        "path": "/",
    },
    "cpu_range_start": 0,
    "monitoring_window": 30,
    "app_sla": 0.08,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,

    "end": 1800,

    "noise_start": 750,
    "noise_scale": 1.3,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 1800,
    "noise_drift_period": 600,
    "seed": 42,

    "generator": {
        "class": "SinGen",
        "params": {"mod": 20, "shift": 22, "period": 600},
    },

    "controller": {
        "class": "GPPPOController",
        "params": {
            "period": 1,
            "init_cores": 4,
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

            "gp_target_mode": "risk_violation",
            "gp_normalize_inputs": True,
            "gp_trust_mode": "outcome",
            "gp_distrust_dwell": 0,

            "gp_lookahead_horizon": 0,
            "gp_adaptive_train": False,
            "gp_drift_threshold": 1.5,
            "gp_min_train_interval": 10,
            "gp_eviction_keep": 0,

            # H4 buffer reset at known drift onset (peak ciclo 2)
            "gp_buffer_reset_at": 750,

            "mu_estimate": 12.5,
            "rho_target": 0.95,
            "tau": 0.5,    # FIX expert: was 0.20 → always-veto with σ_max=0.69
            "kappa": 0.5,  # FIX: was 2.0 → veto saturated at any uncertainty
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
