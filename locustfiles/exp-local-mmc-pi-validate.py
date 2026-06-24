"""Validation run for MMCPIController under CONSTANT load (no drift).

Goal: verify that with stationary load the model converges:
  - μ̂ stabilizes around the expected service rate (M1 Pro Docker Desktop: ~15-17)
  - c_phys stabilizes
  - PI integral remains small (RT below SLA in steady-state)
  - No limit cycle

If the constant-load run looks healthy, we'll add drift and bigger experiments.

LOCAL ONLY — uses path "/" because the locally-launched uwsgi container exposes
the workload on root (vs the AWS gateway path "/function/graph_mst").
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

    # Short validation: 300s steady-state, NO drift
    "end": 300,
    # NB: no noise_start → no noise applied → constant μ_true

    "seed": 42,

    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 50},
    },

    "controller": {
        "class": "MMCPIController",
        "params": {
            "period": 1,
            "init_cores": 4,
            "min_cores": 1,
            "max_cores": 8,
            "st": 1.0,
            # M/M/c floor
            "target_frac": 0.80,
            # μ̂ smoothing
            "mu_ewma_alpha": 0.10,
            # PI feedback
            "kp": 8.0,
            "ki": 2.0,
            "anti_windup_max": 5.0,
            # Docker CPU sampler
            "container_ids": ["graph_set", "graph_quota"],
            "cpu_poll_interval": 2.0,
            # logging
            "enable_log": True,
            "log_dir": "./logs",
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
