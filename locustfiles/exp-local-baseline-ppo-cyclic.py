"""Baseline PPO-only — cyclic workload (SinGen) for stress emergence.

Workload: λ oscilla in [2, 42] ogni 600s. End=1800s = 3 cicli.
Drift @ t=750 (peak ciclo 2) → max stress PPO at peak.
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
    "app_sla": 0.08,  # heavy calib: c=4 viola 19%, buffer mix
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
            "enable_log": True,
            "log_dir": "./logs",
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
