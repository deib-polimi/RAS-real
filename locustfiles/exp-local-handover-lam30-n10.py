"""HandoverPPOController at lam=30, noise=1.0 — THIRD member of the paired
comparison with exp-local-baseline-ppo-lam30-n10 and exp-local-mmc-pi-lam30-n10.

Same workload, same drift, same seed=42. Only the controller differs:
  - PPO alone          → exp-local-baseline-ppo-lam30-n10.py
  - MMCPI alone        → exp-local-mmc-pi-lam30-n10.py
  - PPO + safety       → THIS FILE

Handover trigger calibration (based on observed PPO RT distribution):
  τ_engage  = SLA · 1.2 = 0.30s   (PPO pre-drift p95 = 0.28, no false trigger)
  τ_disengage = SLA · 0.7 = 0.175 (MMCPI post-drift p95 = 0.22, stays in safety)
  K_dwell_min = 15 ticks
  warmup_ticks = 30 (no transitions in first 30s while monitoring window fills)
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
        "class": "HandoverPPOController",
        "params": {
            "period": 1,
            "init_cores": 4,
            "min_cores": 1,
            "max_cores": 8,
            "st": 1.0,
            # PPO
            "train": False,
            "deterministic_eval": True,
            "burst_mode": "none",
            "trend_features": False,
            # Handover FSM
            "tau_engage_mult": 1.2,
            "tau_disengage_mult": 0.7,
            "k_dwell_min": 15,
            "warmup_ticks": 30,
            # Safety (MMCPI) sub-controller
            "target_frac": 0.80,
            "mu_ewma_alpha": 0.10,
            "kp": 8.0,
            "ki": 2.0,
            "anti_windup_max": 5.0,
            # CPU sampler
            "container_ids": ["graph_set", "graph_quota"],
            "cpu_poll_interval": 2.0,
            # Logging
            "enable_log": True,
            "log_dir": "./logs",
        },
    },
}

EXP_NAME = __file__.split("/")[-1].split(".")[0]
from base_experiment import *
setup(EXP_NAME, CONFIG)
