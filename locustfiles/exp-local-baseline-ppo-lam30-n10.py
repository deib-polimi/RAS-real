"""PPO baseline at lam=30, noise=1.0 — PAIRED with exp-local-mmc-pi-lam30-n10.

Same workload, same drift, same seed. Only controller differs (PPO vs MMCPI).
At lam=30 we expect PPO to behave reasonably pre-drift (was 91% violations
at lam=50, hopefully <5% here). The drift then shows the controller's
ability to adapt under OOD service-rate degradation.
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
    "spawn_rate": 1,
    "end": 600,
    "noise_start": 300,
    "noise_scale": 1.0,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 600,
    "noise_drift_period": 300,
    "seed": 42,
    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 30},
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
