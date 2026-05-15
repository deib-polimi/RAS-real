"""EVAL A — PPO without drift (sanity check).

Loads controllers/ppocontroller-none-aws-1h.pt (from exp-aws-train-ppo-1h.py).
Same SinGen distribution as training, no noise.
Expectation: SLA violations ≈ 0%, controller stable on the sinusoidal load.

If this fails → PPO didn't converge; longer training needed before drift tests.
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

    "end": 600,

    "noise_start": 99999,
    "noise_scale": 0.0,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 600,
    "noise_drift_period": 600,
    "seed": 43,

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
