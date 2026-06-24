"""Shared config for the local 'necessity' smoke experiments.

Fairness BY CONSTRUCTION (Codex T13): the COMMON block and the drift scenarios
are defined ONCE here; each locustfile swaps only the controller. This makes it
impossible for baselines to diverge on period / SLA / generator / drift / window
/ cost_coef.

Calibrated 23 giu 2026 (see .claude/tmp/plan-*/calibration-report.md):
  SLA=0.25, N=0.8, SinGen(12.4/22.3/360) → λ_peak=35,
  μ_eff≈13 req/s/core nominal / ≈8 under N=0.8,
  c_nominal=3, c_drift(N=0.8)=6 (recoverable, 1 core headroom).
"""

# --- Fairness-locked common block (IDENTICAL across all controllers) ---
COMMON = {
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
    "noise_type": "avg",
    "noise_scale": 0.8,
    "seed": 42,
}

# Generators (referenced by scenarios)
_SINGEN = {"class": "SinGen", "params": {"mod": 12.4, "shift": 22.3, "period": 360}}
_STAT35 = {"class": "StationaryGen", "params": {"lam": 35}}
_STAT18 = {"class": "StationaryGen", "params": {"lam": 18}}
# Flash-crowd: load jumps 10→50 at t=300 (sentinel 99999 holds the plateau).
_STEP_FC = {"class": "StepGen", "params": {"intervals": [300, 99999], "values": [10, 50]}}

# --- Drift scenarios (only the drift schedule differs) ---
SCENARIOS = {
    # A — SinGen STEP (in-distribution but DILUTED: too easy, PPO never stressed).
    #     Kept for reference / in-distribution baseline.
    "A": {
        "generator": _SINGEN,
        "end": 600, "noise_start": 300, "noise_drift_kind": "step",
        "noise_drift_end": 600, "noise_drift_period": 600,
    },
    # B — SinGen BURSTY/RECURRING (first ON at t=240; tests FSM cycling, T5).
    "B": {
        "generator": _SINGEN,
        "end": 1080, "noise_start": 120, "noise_drift_kind": "bursty",
        "noise_drift_end": 1080, "noise_drift_period": 240,
    },
    # S — StationaryGen(λ=35) STEP — the NECESSITY scenario (sustained load).
    #     Block D: λ=35 N=0.8 → c=5 fails (p95 0.43), c=6 recovers (0.17).
    #     PPO at init=3 is clearly insufficient under drift → must fail.
    "S": {
        "generator": _STAT35,
        "end": 600, "noise_start": 300, "noise_drift_kind": "step",
        "noise_drift_end": 600, "noise_drift_period": 600,
    },
    # S15 — StationaryGen(λ=18) STEP, N=1.5 (strong, recoverable ONLY at low λ:
    #       service time ~0.20s leaves little SLA budget → needs ~6-7 cores).
    #       Probes whether PPO fails despite recovery being feasible.
    "S15": {
        "generator": _STAT18, "noise_scale": 1.5,
        "end": 600, "noise_start": 300, "noise_drift_kind": "step",
        "noise_drift_end": 600, "noise_drift_period": 600,
    },
    # BR50 — bursty μ-drift, period 50s (half-period 25s INSIDE the ~40-70s
    #        feedback dead-band) → pure-feedback PPO can't track it. λ=18 (low),
    #        N=0.8. Probes the control-theory bandwidth prediction.
    "BR50": {
        "generator": _STAT18, "noise_scale": 0.8,
        "end": 600, "noise_start": 100, "noise_drift_kind": "bursty",
        "noise_drift_end": 600, "noise_drift_period": 50,
    },
    # FC — flash-crowd: load STEP 10→50 at t=300 with spawn_rate=50 (fast ramp,
    #      ~1s). No service drift. Tests transient: queue builds before reactive
    #      PPO scales; a feedforward (M/M/c from λ̂) would anticipate.
    "FC": {
        "generator": _STEP_FC, "spawn_rate": 50, "noise_scale": 0.0,
        "end": 600, "noise_start": 99999, "noise_drift_kind": "step",
        "noise_drift_end": 600, "noise_drift_period": 600,
    },
}

# --- Controller param blocks ---
_CTRL_COMMON = {
    "period": 1, "init_cores": 3, "min_cores": 1, "max_cores": 8, "st": 1.0,
    "enable_log": True, "log_dir": "./logs",
}
_PPO_EVAL = {
    "train": False, "deterministic_eval": True, "burst_mode": "none",
    "trend_features": False, "model_suffix": "local-sin-A", "cost_coef": 0.02,
}
_MMCPI = {
    "target_frac": 0.80, "mu_window_s": 30.0,  # fast μ̂ → reactive to drift
    "kp": 8.0, "ki": 2.0,
    "anti_windup_max": 5.0, "container_ids": ["graph_set", "graph_quota"],
    "cpu_poll_interval": 2.0,
}
_FSM = {
    "tau_engage_mult": 1.2, "tau_disengage_mult": 0.7,
    "k_dwell_min": 15, "warmup_ticks": 30,
}

CONTROLLERS = {
    "ppo": {"class": "PPOController",
            "params": {**_CTRL_COMMON, **_PPO_EVAL}},
    "mmcpi": {"class": "MMCPIController",
              "params": {**_CTRL_COMMON, **_MMCPI}},
    "handover": {"class": "HandoverPPOController",
                 "params": {**_CTRL_COMMON, **_PPO_EVAL, **_MMCPI, **_FSM}},
}


def make_config(scenario, controller):
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    if controller not in CONTROLLERS:
        raise ValueError(f"unknown controller {controller!r}")
    cfg = dict(COMMON)
    cfg.update(SCENARIOS[scenario])
    cfg["controller"] = CONTROLLERS[controller]
    return cfg
