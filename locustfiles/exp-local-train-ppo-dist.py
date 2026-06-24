"""PPO TRAINING run on a *distribution* of workloads (no drift, no noise).

Goal: produce a locally-trained PPO whose in-distribution support is the set
{ lam ~ U([15, 30]) }, with the cost penalty enabled (cost_coef=0.01) so that
the learned policy expresses a real cores/latency trade-off (not just
'saturate to max_cores').

Saved as: ./controllers/ppocontroller-none-local.pt  (legacy AWS .pt is kept
intact as ppocontroller-none.legacy.pt).

OOD evaluation will use a separate config that re-introduces noise/drift
outside this training distribution.

Same Docker setup as exp-local-baseline-ppo.py (uwsgi on graph_set / graph_quota,
root path). app_sla aligned to the rest of the local suite (0.08).
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
    "app_sla": 0.08,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,

    # 8 hours of training. ~28800 ticks at period=1 → ≈56 PPO updates (rollout=512).
    "end": 28800,

    # No noise during training — in-distribution = clean nominal regime.
    "noise_start": 28800,
    "noise_scale": 0.0,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 28800,
    "noise_drift_period": 28800,
    "seed": 42,

    # Distribution training: lam resampled every 300s from U([15, 30]).
    "generator": {
        "class": "DistributionGen",
        "params": {
            "lam_min": 15,
            "lam_max": 30,
            "episode_len": 300,
            "seed": 42,
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
            "train": True,
            "deterministic_eval": False,
            "burst_mode": "none",
            "trend_features": False,
            "enable_log": True,
            "log_dir": "./logs",
            "model_suffix": "local",
            "cost_coef": 0.01,
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
