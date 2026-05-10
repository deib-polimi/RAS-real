"""Local SMOKE test of the risk_violation mode (Stage B verification).

60s run, no drift, low lambda. Goal: prove that the new risk_violation
mode runs end-to-end without crashing and produces an envelope-*.jsonl
log. Not for paper-grade evaluation — pure runtime sanity.
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

    "end": 60,

    "noise_start": -1,
    "noise_scale": 0,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 60,
    "noise_drift_period": 60,
    "seed": 42,

    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 20},
    },

    "controller": {
        "class": "GPPPOController",
        "params": {
            "period": 1,
            "init_cores": 4,
            "min_cores": 1.0,
            "max_cores": 8,
            "st": 1.0,
            "st_max": 1.0,
            "min_st": 1.0,
            "train": False,
            "deterministic_eval": True,
            "burst_mode": "none",
            "trend_features": False,
            "enable_log": True,
            "log_dir": "./logs",

            "bc": 0.0,
            "dc": 0.0,
            "pi_anti_windup": False,
            "pi_e_clip": 10.0,
            "pi_error_form": "linear",
            "pi_rt_deadband_frac": 0.30,

            "gp_train_start": 5,
            "gp_min_samples": 10,
            "gp_train_freq": 30,
            "gp_max_buffer_size": 200,
            "pi_start_time": 2,
            "gp_time_period": 200,
            "gp_async": False,

            # Step 1 v3: risk_violation mode
            "gp_target_mode": "risk_violation",
            "gp_normalize_inputs": True,
            "gp_trust_mode": "outcome",
            "gp_distrust_dwell": 0,

            "gp_lookahead_horizon": 0,
            "gp_adaptive_train": False,
            "gp_drift_threshold": 1.5,
            "gp_min_train_interval": 10,
            "gp_eviction_keep": 0,

            # New v3 knobs
            "mu_estimate": 17.0,
            "rho_target": 0.7,
            "tau": 0.20,
            "kappa": 2.0,
            "alpha_clamp": 0.7,
            "dwell_ticks_min": 3,
            "dwell_ticks_max": 30,
            "floor_method": "utilization",
            "master_seed": 42,
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
