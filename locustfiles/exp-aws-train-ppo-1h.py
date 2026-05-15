"""PPO TRAINING — AWS 31-core box, 1h sprint.

Calibrated 2026-05-15 (logs/calibration-20260515-092904.jsonl):
  μ̂/core = 14.48 req/s (CV 3.4%, linear 2-8c)
  Cap @16c pre-drift = 232 req/s; post-drift (noise=1.5) = 92.7 req/s
  Ceiling uwsgi = 16 cores (graph_set -p 15 + graph_quota -p 1)

Training distribution: SinGen mid-range, ρ_pre ∈ [0.22, 0.65]
  shift=100, mod=50, period=360s  →  lam ∈ [50, 150]
  Pre-drift: forces real scaling decisions (1-2c at trough, ~10c at peak).
  No drift here — keep training in-distribution clean.

Output checkpoint: controllers/ppocontroller-none-aws-1h.pt
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

    "end": 3600,

    "noise_start": 99999,
    "noise_scale": 0.0,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 3600,
    "noise_drift_period": 3600,
    "seed": 42,

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
            "train": True,
            "deterministic_eval": False,
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
