"""PPO + bidirectional GP guardrail (B1 — gp_target_mode="signed_shortfall").

The GP target is SIGNED:
    target = cores · (RT - SLA) / SLA
positive when RT > SLA (need more cores), negative when RT < SLA
(have excess cores). The `max(0, comp)` clamp in `control()` is
disabled for this mode, so the GP can pull cores BELOW PPO's choice
when PPO over-provisions (the OOD failure mode of run3b).

`gp_percentile=50` → use the unbiased mean of the GP posterior, no
upward conservatism bias from uncertainty (which was the cause of
pre-drift over-provisioning in legacy mode).

PI is muted (bc=dc=0) — the guardrail is purely GP-driven. This is the
"PPO+GP" arm of the cost-vs-violations Pareto comparison.

Pair with `exp-paper-baseline-ppo.py`. Same workload, drift, init/min/
max cores. Only the controller differs (and its bidirectional GP).

NOTE: noise_scale is set to 1.5 pending calibration confirmation.
"""

CONFIG = {
    "hosts": ["http://localhost:8080", "http://localhost:8081"],
    "containerIds": ["graph_set", "graph_quota"],
    "request": {
        "method": "POST",
        "data": {"size": 25000},
        "headers": {"Content-Type": "application/json"},
        "path": "/function/graph_mst",
    },
    "cpu_range_start": 0,
    "monitoring_window": 30,
    "app_sla": 0.25,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,

    "end": 1200,

    # Drift: noise_scale=1.3 — must match exp-paper-baseline-ppo.py.
    "noise_start": 300,
    "noise_scale": 1.3,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 900,
    "noise_drift_period": 300,
    "seed": 42,

    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 40},
    },

    "controller": {
        "class": "GPPPOController",
        "params": {
            "period": 1,
            "init_cores": 4,
            "min_cores": 1.0,         # safety floor (signed GP can't go below)
            "max_cores": 16,
            "st": 1.0,
            "st_max": 1.0,
            "min_st": 1.0,
            "train": False,
            "deterministic_eval": True,
            "burst_mode": "none",
            "trend_features": False,
            "enable_log": True,
            "log_dir": "./logs",

            # PI muted — guardrail is GP-only
            "bc": 0.0,
            "dc": 0.0,
            "pi_anti_windup": False,
            "pi_e_clip": 10.0,
            "pi_error_form": "linear",
            "pi_rt_deadband_frac": 0.30,

            # GP scheduling
            "gp_train_start": 10,
            "gp_min_samples": 30,
            "gp_train_freq": 50,
            "gp_max_buffer_size": 500,
            "pi_start_time": 5,
            "gp_time_period": 200,
            "gp_async": True,

            # B1: bidirectional guardrail
            "gp_target_mode": "signed_shortfall",   # signed target (+/-)
            "gp_percentile": 50,                    # unbiased mean (no uncertainty bias)
            "gp_normalize_inputs": True,
            "gp_trust_mode": "outcome",
            "gp_distrust_dwell": 0,

            # Lookahead disabled for signed mode (semantics tied to legacy max-RT)
            "gp_lookahead_horizon": 0,
            "gp_adaptive_train": False,
            "gp_drift_threshold": 1.5,
            "gp_min_train_interval": 10,
            "gp_eviction_keep": 0,
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
