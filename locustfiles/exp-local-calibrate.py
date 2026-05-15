"""Principled μ_eff calibration via the same Locust + request_maker +
monitoring path used by experiments.

Schedule: 4 slots × 630s each (30s warmup + 600s measurement).
Cores: [2, 4, 6, 8] — tuned for Mac M1 (8 physical cores).
Lam adaptive: ~0.75 × cores × μ_expected(=12) → operating range ρ≈0.75.

Output JSONL log → parse with tools/parse_calibration.py for:
  - per-cores μ̂ via Operational Utilization Law (X / U)
  - aggregated μ̂_avg, capacity at max_cores
  - recommended SLA + workload range for downstream PPO training.

NO drift noise (pre-drift only). Post-drift μ̂ inferred as μ̂_avg / (1+noise_scale)
where noise_scale is the experiment drift severity (typically 1.5).
"""

# (t_start_s, cores, lam) — schedule MASTER
SCHEDULE = [
    (   0, 2, 18),   #   0..630s   c=2, lam=18 (ρ≈0.75)
    ( 630, 4, 36),   # 630..1260s  c=4, lam=36
    (1260, 6, 54),   # 1260..1890s c=6, lam=54
    (1890, 8, 72),   # 1890..2520s c=8, lam=72
]
END = 2520

# Extract per-component schedules
SCHEDULE_CORES = [(t, c) for (t, c, l) in SCHEDULE]
SCHEDULE_LAMS = [(t, l) for (t, c, l) in SCHEDULE]

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

    "end": END,

    # NO drift during calibration (clean pre-drift μ̂ measurement).
    "noise_start": END + 1,
    "noise_scale": 0.0,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": END,
    "noise_drift_period": END,
    "seed": 42,

    "generator": {
        "class": "CalibrationGen",
        "params": {
            "schedule": SCHEDULE_LAMS,
        },
    },

    "controller": {
        "class": "CalibrationController",
        "params": {
            "period": 1,
            "schedule": SCHEDULE_CORES,
            "min_cores": 1,
            # max_cores MUST be ≤ host's os.cpu_count() because controller_loop
            # pins the quota container to cpuset_cpus=<max_cores-1>.
            # Mac M1 has 8 cores → max_cores=8. On AWS bumps to 16.
            "max_cores": 16,
            "st": 1.0,
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
