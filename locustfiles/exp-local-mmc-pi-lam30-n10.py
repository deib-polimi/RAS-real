"""MMCPI at lam=30, noise=1.0 — PAIRED with exp-local-baseline-ppo-lam30-n10.

Rationale: at lam=50 PPO was OOD even pre-drift (91% violations). Reducing
lam to 30 should put PPO back in distribution (since at c=2 the system is
still stable). Then noise=1.0 doubles request size → μ drops ~50%, drift
is meaningful but recoverable with max_cores=8.

PREDICTIONS (M/M/c with measured μ_per_core ≈ 17.7):
   Pre-drift:  λ≈30, μ̂≈17.7 → c_phys = 3, RT ≈ 0.07s
   Post-drift: λ≈30, μ̂≈8.85 → c_phys = 5, RT ≈ 0.13s
   Drift severity: -50% μ (similar to AWS noise=1.3 effect)
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
    "noise_scale": 1.0,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 600,
    "noise_drift_period": 300,
    "seed": 42,
    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 30},
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
