r"""Diagnostic 600s run — captures the GP "training stuck" pattern with verbose
[GP-WORKER] / [GP-TRAIN] / [GP-CHECK] / [GP-FLAG] / [GP-PRED] logs.

Differences vs exp-paper-canonical.py:
  - end:        1200 -> 600   (we just need to see the bug repeat)
  - noise_start: 300 -> 200   (drift onset earlier so we observe post-drift GP behaviour)

Everything else is IDENTICAL to run #3 so the diagnostic apples-to-apples.

After the run, grep on:
  grep -E '\[GP-(WORKER|TRAIN|CHECK|FLAG|PRED)\]' <stdout>

Decision tree (single line per case):
  C1 (sklearn slow):  [GP-WORKER] FIT_DONE arrives but >tick budget; check elapsed climbs
  C2 (queue deadlock): [GP-WORKER] PUT_QUEUE NEVER appears, alive=True forever
  C3 (subprocess crash): [GP-WORKER] CRASH or alive=False + exit!=0 + qsize=0
  C4 (parent never reads queue): alive=False + qsize=1 lingering
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

    # 10-min diagnostic run (vs 20-min canonical).
    "end": 600,

    "noise_start": 200,            # drift onset earlier — we want post-drift GP behaviour fast
    "noise_scale": 2.0,
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
            "min_cores": 0.0,
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

            # PI muted (run #3 ablation — focus on PPO+GP)
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
            "gp_async": True,                     # under investigation

            # GP architectural fixes
            "gp_target_mode": "sla_shortfall",
            "gp_normalize_inputs": True,
            "gp_trust_mode": "outcome",
            "gp_distrust_dwell": 0,

            # Pareto knobs (same as run #3)
            "gp_percentile": 95,
            "gp_lookahead_horizon": 5,
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
