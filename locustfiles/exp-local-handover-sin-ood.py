"""PPO + Guardrail (HandoverPPOController) — sinusoidal workload + drift step at t=400.

A/B paired with exp-local-ppoonly-sin-ood. Same SinGen workload (in-distribution
for PPO), same drift, controller=HandoverPPOController activates the MMCPI
safety layer (online μ̂ via Utilization Law + Erlang-C floor + add-only PI).

Loads model: controllers/ppocontroller-none-local-sin.pt
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

    "end": 900,

    "noise_start": 400,
    "noise_scale": 1.5,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 900,
    "noise_drift_period": 500,
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
        "class": "HandoverPPOController",
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
            "model_suffix": "local-sin-A",
            "cost_coef": 0.02,
            # Handover FSM thresholds
            "tau_engage_mult": 1.2,
            "tau_disengage_mult": 0.7,
            "k_dwell_min": 15,
            "warmup_ticks": 30,
            # MMCPI safety sub-controller
            "target_frac": 0.80,
            "mu_ewma_alpha": 0.10,
            "kp": 8.0,
            "ki": 2.0,
            "anti_windup_max": 5.0,
            # CRITICAL: container_ids enable online μ̂ via Docker CPU stats
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
