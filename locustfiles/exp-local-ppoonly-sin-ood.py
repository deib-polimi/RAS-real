"""PPO ONLY (no guardrail) — sinusoidal workload + drift step at t=400.

Paired A/B baseline for exp-local-handover-sin-ood. Same SinGen workload as
training (in-distribution), same drift, only difference is the controller
class.

Loads model: controllers/ppocontroller-none-local-sin.pt
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
    "app_sla": 0.242,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,

    "end": 900,

    # Step drift at t=400, payload ~2.5× post-drift (noise_scale=1.5 avg).
    "noise_start": 400,
    "noise_scale": 1.5,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 900,
    "noise_drift_period": 500,
    "seed": 42,

    "generator": {
        "class": "SinGen",
        "params": {
            "mod": 12.4,
            "shift": 22.3,
            "period": 360,
        },
    },

    "controller": {
        "class": "PPOController",
        "params": {
            "period": 1,
            "init_cores": 4,
            "min_cores": 1,
            "max_cores": 8,
            "st": 1.0,
            "train": False,
            "deterministic_eval": True,
            "burst_mode": "none",
            "trend_features": False,
            "model_suffix": "local-sin-A",
            "cost_coef": 0.02,
            "enable_log": True,
            "log_dir": "./logs",
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
