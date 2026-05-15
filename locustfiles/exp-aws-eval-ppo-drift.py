"""EVAL B — PPO under step drift (the failure baseline for the paper).

Same checkpoint as Eval A.
Step drift noise_scale=1.5 at t=300s.
Post-drift μ = 14.48 / 2.5 = 5.79 → cap @16c = 92.7 req/s.
At lam_peak=150 → ρ_post_peak = 1.62 → system goes overloaded.
PPO cannot adapt (no drift signal in its state) → SLA violations expected
in 50-100% range during drift window.

This is the curve we expect the guardrail to flatten in Eval C.
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
        "class": "PPOController",
        "params": {
            "period": 1,
            "init_cores": 8,
            "min_cores": 1,
            "max_cores": 16,
            "st": 1.0,
            "train": False,
            "deterministic_eval": True,
            "burst_mode": "none",
            "trend_features": False,
            "enable_log": True,
            "log_dir": "./logs",
            "model_suffix": "aws-1h",
            "cost_coef": 0.02,
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
