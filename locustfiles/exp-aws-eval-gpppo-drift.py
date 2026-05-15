"""EVAL C — GPPPO under step drift (the win-condition for the paper).

Same checkpoint, same workload, same drift profile as Eval B.
Only the controller class changes: PPO → GPPPO (PPO + GP guardrail + PI).
mu_estimate = 14.48 (AWS calibration); rho_target = 0.7 → PI commands
additional cores when PPO's choice is insufficient.

Expectation: SLA violations < 10% (vs. >50% with bare PPO in Eval B).
The PI compensation activates within ~30 ticks after drift onset.
"""

CONFIG = {
    "hosts": ["http://localhost:8080", "http://localhost:8081"],
    "containerIds": ["graph_set", "graph_quota"],
    "request": {
        "method": "POST",
        "data": {"size": 25000},
        "headers": {"Content-Type": "application/json"},
        "path": "/",
    },
    "cpu_range_start": 0,
    "monitoring_window": 30,
    "app_sla": 0.25,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 10,

    "end": 900,

    "noise_start": 300,
    "noise_scale": 1.5,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 900,
    "noise_drift_period": 600,
    "seed": 44,

    "generator": {
        "class": "SinGen",
        "params": {
            "mod": 50,
            "shift": 100,
            "period": 360,
        },
    },

    "controller": {
        "class": "GPPPOController",
        "params": {
            "period": 1,
            "init_cores": 8,
            "min_cores": 1,
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
            "model_suffix": "aws-1h",
            "cost_coef": 0.02,

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

            "gp_buffer_reset_at": 300,

            "mu_estimate": 14.48,
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
