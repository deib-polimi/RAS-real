"""Local PPO baseline — PAIRED with exp-local-mmc-pi-drift.py (noise_scale=0.7).

Same workload, same drift profile, same seed, same SLA, same init/max cores
as the MMCPI calibrated drift run. ONLY the controller differs:
  - This file: PPOController (the trained PPO model)
  - MMCPI run: MMCPIController (physics-informed M/M/c + PI)

Purpose: head-to-head comparison on identical conditions, so we can attribute
performance differences directly to the controller choice.

Calibration rationale (matches exp-local-mmc-pi-drift):
  noise_scale = 0.7  → μ_post ≈ 8.4 (down from ~14-17 pre)
                     → recoverable with max_cores=8

PREDICTIONS to falsify:
  - PPO was trained on AWS-style workload (noise_scale=1.3, μ_drop ~50%)
  - On this local Docker (fixed graph_mst), the equivalent drop is at 0.7
  - Question: does PPO transfer to this regime, or does it misbehave?
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
    "noise_scale": 0.7,            # ← paired with MMCPI run
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 600,
    "noise_drift_period": 300,
    "seed": 42,

    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 50},
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
