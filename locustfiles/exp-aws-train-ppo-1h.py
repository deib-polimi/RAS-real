"""PPO TRAINING — AWS 31-core box, 3h.

Calibrated 2026-05-15 (logs/calibration-20260515-092904.jsonl):
  μ̂/core measured 15.18(c=2) → 14.10(c=8), asymptote ~14.0 at high c
  Cap @16c pre-drift ≈ 216 req/s; post-drift (noise=1.5) ≈ 89.6 req/s
  Ceiling uwsgi = 16 cores (graph_set -p 15 + graph_quota -p 1)

Training distribution: SinGen narrow (drift-recoverable at max cores)
  shift=50, mod=20, period=360s  →  lam ∈ [30, 70]
  Pre-drift ρ ∈ [0.13, 0.32]; post-drift ρ_peak ≈ 0.78 → clean recovery feasible.
  Optimal cores: 3 (trough) → 6 (peak).

cost_coef=0.15 (was 0.02): first value above the anti-ratchet breakeven (0.12).
  At c=16 cost = 0.15; equivalent to ~150ms violation → PPO actively scales down
  when cap is sufficient. Validated via codex cross-review.

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

    "end": 10800,

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
            "mod": 20,
            "shift": 50,
            "period": 360,
        },
    },

    "controller": {
        "class": "PPOController",
        "params": {
            "period": 1,
            "init_cores": 4,
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
            "cost_coef": 0.15,
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
