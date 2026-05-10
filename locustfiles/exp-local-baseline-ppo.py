"""Local baseline PPO-only run — companion to exp-local-bidirect.py.

LOCAL ONLY — DO NOT RUN ON AWS as-is. The request path is "/" because the
locally-launched uwsgi container exposes the workload on root.

Same workload, drift, init/min/max cores as exp-local-bidirect.py — only the
controller differs (no GP, no PI, no buffer reset). Pair these two runs to
get a local cost-vs-violations comparison without AWS overhead.

Calibrated for this machine (M1 Pro, Docker Desktop 8 vCPU):
  μ_eff/core    = 17.3 (c≤4) | 13.7 (c=8, VM saturating)
  init_cores    = 4
  max_cores     = 8
  lam           = 50  (ρ_pre at c=4 ≈ 0.74 → marginal SLA → PPO must scale up)

Hypothesis paired with bidirect: pure PPO under drift will saturate cores
near max (high cost, ok SLA); the bidirectional GP+reset SHOULD give
similar/lower violations at lower cost. If the bidirect run beats PPO on
both metrics, H4 is the dominant cause and the buffer-reset fix is on the
right track.
"""

CONFIG = {
    "hosts": ["http://localhost:8080", "http://localhost:8081"],
    "containerIds": ["graph_set", "graph_quota"],
    "request": {
        "method": "POST",
        "data": {"size": 25000},
        "headers": {"Content-Type": "application/json"},
        # LOCAL: workload exposed on root path (no OpenFaaS gateway here).
        "path": "/",
    },
    "cpu_range_start": 0,
    "monitoring_window": 30,
    "app_sla": 0.25,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,

    "end": 600,

    # Drift: step at t=300, persistent until end. Same as exp-local-bidirect.py.
    "noise_start": 300,
    "noise_scale": 1.3,
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
