"""Workload-matched calibration — cores fixed at 4.

Runs 600s with the EXACT same workload as exp-local-bidirect-risk-balanced.py
but with cores frozen via StaticController. Output: RT distribution at c=4.
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
    "app_sla": 0.25,  # placeholder, not used during static calibration
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,

    "end": 600,

    "noise_start": -1,
    "noise_scale": 0,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 600,
    "noise_drift_period": 600,
    "seed": 42,

    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 22},
    },

    "controller": {
        "class": "StaticController",
        "params": {
            "period": 1,
            "init_cores": 4,
            "min_cores": 4,
            "max_cores": 4,
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
