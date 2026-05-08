"""Baseline PPO-only run for the cost-vs-violations Pareto comparison.

Pure PPO — no GP guardrail, no PI compensation. Designed to expose the
out-of-distribution behaviour of PPO under drift: cores tend to saturate
at max_cores regardless of actual demand, so this baseline is expected
to have HIGH cost (cores·time) and (likely) FEWER SLA violations than
GPPPO bidirectional, simply because it stays at ceiling.

Pair with `exp-paper-bidirect-gp.py`. The story we want to tell:
    PPO_only:        high cost, low violations  → expensive safety
    PPO+GP_bidir:    low cost,  similar viol.    → guardrail keeps cost bounded

Same workload, drift, init/min/max cores. Only the controller class differs.

NOTE: noise_scale is set to 1.5 pending calibration confirmation. Update
this value (and the matching one in exp-paper-bidirect-gp.py) once we
have calibrate_mu output for noise=1.0/1.5/2.0.
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

    # Drift: pending calibration. 1.5 is current best guess (recoverable in 16 cores).
    "noise_start": 300,
    "noise_scale": 1.5,
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
        "class": "PPOController",
        "params": {
            "period": 1,
            "init_cores": 4,
            "min_cores": 1,
            "max_cores": 16,
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
