"""PPO TRAINING with sinusoidal workload (3h, calibrated parameters).

Parameters derived from calibration report (tools/parse_calibration.py)
on Mac M1 8-core, measured μ̂/core = 15.50 ± 0.75 (CV=4.9%):

  SinGen: mod=12.4, shift=22.3, period=360s → lam ∈ [9.9, 34.7]
  SLA: 0.242s (= 1.5 × 1/μ̂_post with floor 150ms)
  Drift severity assumed for downstream OOD test: noise_scale=1.5

Capacity check:
  pre-drift (μ=15.5, 8c = 124 req/s):  ρ_peak = 34.7/124 = 0.28 ✓ comfortable
  post-drift (μ=6.2, 8c =  49.6 req/s): ρ_peak = 34.7/49.6 = 0.70 ✓ guardrail margin

Training: 3h (10800s) = 30 sinusoid cycles, ~21 PPO updates.

Saved as controllers/ppocontroller-none-local-sin.pt
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

    "end": 18000,

    # No noise during training (clean in-distribution data).
    "noise_start": 10000,
    "noise_scale": 0.0,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 3600,
    "noise_drift_period": 3600,
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
            "init_cores": 6,
            "min_cores": 1,
            "max_cores": 8,
            "st": 1.0,
            "train": True,
            "deterministic_eval": False,
            "burst_mode": "none",
            "trend_features": False,
            "enable_log": True,
            "log_dir": "./logs",
            "model_suffix": "local-sin-A",
            "cost_coef": 0.02,
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
