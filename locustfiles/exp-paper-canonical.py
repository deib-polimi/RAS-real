"""Cloud-canonical experiment template for the paper headline runs.

This template targets the local Docker plant (graph_set / graph_quota
containers exposing /function/graph_mst) and surfaces every GPPPO knob
explicitly so reviewers can read the configuration without spelunking
controller source.

Drift knobs (request_maker.py) — μ_eff degradation via payload size:
  - noise_drift_kind ∈ {"step", "ramp", "bursty"}
  - noise_drift_end   (ramp endpoint, in seconds; only for "ramp")
  - noise_drift_period (full cycle in seconds; only for "bursty")

Workload generator:
  - StationaryGen(lam): constant load (the recommended workload for
    μ-drift studies, since drift is the only source of non-stationarity).

Controller knobs (GPPPOController) — all defaults preserve legacy behaviour:
  - PI subsystem:        pi_anti_windup, pi_e_clip, pi_error_form,
                         pi_rt_deadband_frac
  - GP target:           gp_target_mode = "sla_shortfall" (GP-R2 fix)
  - GP inputs:           gp_normalize_inputs = True (GP-R1 fix)
  - GP percentile (β):   gp_percentile  ∈ {50, 75, 90, 95, 99}
  - GP lookahead (H):    gp_lookahead_horizon ∈ {0, 1, 5, 10}
  - GP eviction (E):     gp_adaptive_train + gp_eviction_keep
  - PPO eval mode:       deterministic_eval = True (RL-R3 fix)
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

    # 20-min run with drift onset at 5min, settled by 15min.
    "end": 1200,

    # μ-drift (payload-size noise) — pick ONE profile by setting noise_drift_kind:
    # step:   noise_scale jumps from 0 to value at noise_start
    # ramp:   noise_scale grows linearly from noise_start to noise_drift_end
    # bursty: noise_scale toggles ON/OFF every (noise_drift_period/2) seconds
    "noise_start": 300,
    "noise_scale": 1.5,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 900,        # used only when kind="ramp"
    "noise_drift_period": 300,     # used only when kind="bursty"
    "seed": 42,

    # Stationary λ — the only source of variability is the μ drift above.
    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 22},
    },

    "controller": {
        "class": "GPPPOController",
        "params": {
            # Base controller
            "period": 1,
            "init_cores": 1,
            "min_cores": 1.0,
            "max_cores": 28,
            "st": 1.0,
            "train": False,
            "deterministic_eval": True,           # RL-R3
            "burst_mode": "none",
            "trend_features": False,
            "enable_log": True,
            "log_dir": "./logs",

            # Auxiliary PI (post-tuning values)
            "bc": 0.3,
            "dc": 0.1,
            "pi_anti_windup": True,               # CT-R2
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
            "gp_async": True,                     # mp.Process for production

            # GP architectural fixes
            "gp_target_mode": "sla_shortfall",    # GP-R2
            "gp_normalize_inputs": True,          # GP-R1
            "gp_trust_mode": "outcome",           # SAFE-R3 ("calibration") optional
            "gp_distrust_dwell": 0,               # SAFE-R1 (set ≥30 for paper)

            # The three Pareto knobs (paper headline)
            "gp_percentile": 95,                  # β
            "gp_lookahead_horizon": 5,            # H
            "gp_adaptive_train": True,            # E (drift-aware eviction)
            "gp_drift_threshold": 1.5,
            "gp_min_train_interval": 10,
            "gp_eviction_keep": 40,
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
