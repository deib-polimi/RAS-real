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
    "noise_scale": 2.0,            # ×3 payload at drift → μ_eff drops to ~6.5/core
                                    # (recoverable with c=10 inside max_cores=16)
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 900,        # used only when kind="ramp"
    "noise_drift_period": 300,     # used only when kind="bursty"
    "seed": 42,

    # Stationary λ — the only source of variability is the μ drift above.
    # λ=40 user pushes the system close to saturation pre-drift (ρ≈0.77 at c=4)
    # so the GP target ("sla_shortfall") sees non-zero values during the
    # transient and can actually learn — at λ=22 the system was over-provisioned
    # at any feasible c, leaving the GP with target=0 forever.
    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 40},
    },

    "controller": {
        "class": "GPPPOController",
        "params": {
            # Base controller. Sizing rationale (post run #2 root-cause analysis):
            #   - init_cores=4: cold-start at ρ=0.77 (stable) at λ=40, μ=13/core.
            #     Avoids cold-start violations now that the PI safety net is OFF.
            #   - min_cores=0.0: removes the "+1 core bonus" from controller_loop's
            #     `quotaCores = max(min_cores, cores-setCores)` line.
            #   - max_cores=16: matches the calibrated host (16 cores tested).
            #   - st_max=min_st=1.0: disables auto-tune ST (confound — it was
            #     doing the GP's job by dynamically tightening the setpoint).
            "period": 1,
            "init_cores": 4,
            "min_cores": 0.0,
            "max_cores": 16,
            "st": 1.0,
            "st_max": 1.0,
            "min_st": 1.0,
            "train": False,
            "deterministic_eval": True,           # RL-R3
            "burst_mode": "none",
            "trend_features": False,
            "enable_log": True,
            "log_dir": "./logs",

            # Auxiliary PI — DISABLED for run #3 (PPO+GP-only ablation).
            # bc=dc=0 makes the PI's `cores_unsat = xc_prec + 0` a fixed point at
            # min_cores=0, so `pi_compensation = 0 - ppo_cores < 0`, and the
            # guardrail `max(0, comp)` zeroes it. Net effect: PI is muted in
            # both Phase 1 (pre-GP) and the GP-distrust fallback path.
            # NOTE: a residual seam remains in CTControllerScaleX:69-70 (PI
            # floors `cores ≥ init_cores` for the first 20 ticks). For a fully
            # clean ablation we would add a `pi_enabled` flag — deferred.
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
            "gp_async": True,                     # mp.Process for production

            # GP architectural fixes
            "gp_target_mode": "sla_shortfall",    # GP-R2
            "gp_normalize_inputs": True,          # GP-R1
            "gp_trust_mode": "outcome",           # SAFE-R3 ("calibration") optional
            "gp_distrust_dwell": 0,               # SAFE-R1 (set ≥30 for paper)

            # The three Pareto knobs (paper headline).
            # adaptive_train DISABLED for run #3: with async training time
            # (~1.05s) ≥ tick (1s), drift-detection retriggered retraining on
            # every tick, leaving the GP perpetually in-training (predict→0).
            # Now retraining only follows gp_train_freq=50 schedule.
            "gp_percentile": 95,                  # β
            "gp_lookahead_horizon": 5,            # H
            "gp_adaptive_train": False,           # E disabled (was the loop bug)
            "gp_drift_threshold": 1.5,            # unused with adaptive_train=False
            "gp_min_train_interval": 10,          # unused with adaptive_train=False
            "gp_eviction_keep": 0,                # unused with adaptive_train=False
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
