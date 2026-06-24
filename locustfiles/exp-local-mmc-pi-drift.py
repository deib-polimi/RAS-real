"""Drift run for MMCPIController — first end-to-end test of the physics-informed
guardrail under workload OOD on the local Docker microservice.

PROFILE: 600s total
   [  0 .. 300] s : no drift  (mirrors exp-local-mmc-pi-validate)
   [300 .. 600] s : step drift, noise_scale=1.3 (service size +30%)

EXPECTED BEHAVIOUR (predictions, to be falsified by the run):
   pre-drift:    λ≈46, μ̂≈17, c_phys=4, RT≈0.08s, pi_I=0
   transient:    RT spikes briefly, μ̂ drops via EWMA in ~10-30s, PI activates
   post-drift:   μ̂≈13, c_phys rises to 5, RT recovers below SLA, pi_I returns
                 toward 0 once c_phys absorbs the load

PAIRING: this is the COMPANION to exp-local-baseline-ppo.py — same noise profile,
same SLA, same λ. The two are designed for cost/violation comparison.
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

    # Step drift at t=300, persistent until end (=600).
    "noise_start": 300,
    # noise_scale calibrated for local M1 Docker: 0.7 gives μ_post ≈ 8.4 (vs
    # μ_pre ≈ 14), recoverable with max_cores=8. With 1.3 the local service
    # saturates max cores (μ_post drops to ~6 which is below the M/M/c stability
    # threshold ρ<1 at c=8). The AWS run uses 1.3 because the AWS service has
    # different baseline μ — the equivalent drop magnitude on local needs 0.7.
    "noise_scale": 0.7,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": 600,
    "noise_drift_period": 300,

    "seed": 42,

    "generator": {
        "class": "StationaryGen",
        "params": {"lam": 50},
    },

    "controller": {
        "class": "MMCPIController",
        "params": {
            "period": 1,
            "init_cores": 4,
            "min_cores": 1,
            "max_cores": 8,
            "st": 1.0,
            # M/M/c floor
            "target_frac": 0.80,
            # μ̂ smoothing
            "mu_ewma_alpha": 0.10,
            # PI feedback (now symmetric anti-windup)
            "kp": 8.0,
            "ki": 2.0,
            "anti_windup_max": 5.0,
            # Docker CPU sampler
            "container_ids": ["graph_set", "graph_quota"],
            "cpu_poll_interval": 2.0,
            # logging
            "enable_log": True,
            "log_dir": "./logs",
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
