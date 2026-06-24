"""Strong-drift run for MMCPIController — same as exp-local-mmc-pi-drift but
with noise_scale=2.5 to actually push the local Docker out of distribution.

CONTEXT: the noise_scale=1.3 run (drift mite) only dropped μ̂ by ~5% — the local
M1 absorbed it. Here we use noise_scale=2.5 (service size 2.5x) to force a
meaningful drop in effective μ.

PREDICTIONS (μ_pre ≈ 17 from validate):
   linear extrapolation: μ_post ≈ 17/2.5 = 6.8 req/s/core
   empirical (1.3→5%): μ_post probably 10-14 (compound effects)
   stability: at λ=46, need c·μ > 46. If μ falls below 6, even c=8 unstable.
   expected c_phys to climb to 5-7 depending on actual μ drop.
   expected PI to activate during transient → fix verification in vivo.
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
    "noise_scale": 2.5,            # ← strong drift
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
        "class": "MMCPIController",
        "params": {
            "period": 1,
            "init_cores": 4,
            "min_cores": 1,
            "max_cores": 8,
            "st": 1.0,
            "target_frac": 0.80,
            "mu_ewma_alpha": 0.10,
            "kp": 8.0,
            "ki": 2.0,
            "anti_windup_max": 5.0,
            "container_ids": ["graph_set", "graph_quota"],
            "cpu_poll_interval": 2.0,
            "enable_log": True,
            "log_dir": "./logs",
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
