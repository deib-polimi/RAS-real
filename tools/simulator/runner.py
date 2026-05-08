"""Simulation loop: drive a controller against the synthetic plant for N ticks."""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
from typing import Callable

import numpy as np

from .monitoring import SyntheticMonitoring
from .plant import MMcPlant
from .plant_mmc import MMcDiscretePlant


def simulate_one(
    architecture_factory: Callable,
    workload_fn: Callable[[int], float],
    *,
    n_ticks: int = 400,
    sla: float = 0.2,
    service_rate: float = 10.0,
    noise_std: float = 0.10,
    noise_dist: str = "gaussian",
    init_cores: float = 4.0,
    min_cores: float = 1.0,
    max_cores: float = 20.0,
    st: float = 0.8,
    period: int = 1,
    train: bool = True,
    train_freeze_at: int | None = None,
    seed: int = 0,
    extra_common: dict | None = None,
    log_path: Path | None = None,
    plant_model: str = "fluid",
    service_drift_fn=None,
) -> list[dict]:
    """Run one simulation. Returns per-tick history."""
    rng = np.random.default_rng(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
    except Exception:
        pass

    if plant_model == "fluid":
        plant = MMcPlant(service_rate=service_rate, sla=sla,
                         noise_std=noise_std, noise_dist=noise_dist, rng=rng,
                         service_drift_fn=service_drift_fn)
    elif plant_model == "mmc":
        plant = MMcDiscretePlant(service_rate=service_rate, sla=sla,
                                 noise_std=noise_std, noise_dist=noise_dist, rng=rng,
                                 service_drift_fn=service_drift_fn)
    else:
        raise ValueError(f"unknown plant_model: {plant_model!r} (choose 'fluid' or 'mmc')")
    monitoring = SyntheticMonitoring(plant)

    common = {
        "period": period,
        "init_cores": init_cores,
        "min_cores": min_cores,
        "max_cores": max_cores,
        "st": st,
        "train": train,
    }
    if extra_common:
        common.update(extra_common)

    # Redirect controller stdout (debug prints) to a per-run log file so the
    # terminal output stays clean. If log_path is None, swallow it.
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_sink = open(log_path, "w")
    else:
        log_sink = io.StringIO()

    with contextlib.redirect_stdout(log_sink):
        controller = architecture_factory(common)
        controller.setMonitoring(monitoring)
        controller.setSLA(sla)

        history = _run_loop(controller, monitoring, plant, workload_fn,
                            n_ticks=n_ticks, sla=sla, train_freeze_at=train_freeze_at)

    log_sink.close()
    return history


def _run_loop(controller, monitoring, plant, workload_fn, *, n_ticks, sla,
              train_freeze_at):
    history: list[dict] = []
    for t in range(n_ticks):
        # Optional: freeze PPO training mid-run (e.g. before drift onset)
        if train_freeze_at is not None and t == train_freeze_at:
            for attr in ("train",):
                if hasattr(controller, attr):
                    setattr(controller, attr, False)
            for inner in ("ppo",):  # PPOPIController.ppo
                if hasattr(controller, inner):
                    setattr(getattr(controller, inner), "train", False)

        lam = workload_fn(t)
        # 1. Plant produces RT for the cores chosen at the previous tick
        plant.step(arrival_rate=lam, cores=controller.cores)
        monitoring.update()

        # 2. Controller observes RT and decides next cores
        controller.tick(float(t))

        # 3. Record snapshot
        history.append({
            "t": t,
            "lambda": lam,
            "rt": plant.last_rt,
            "rho": plant.last_rho,
            "cores": float(controller.cores),
            "sla_violated": plant.last_rt > sla,
        })

    # Cleanup any background process (GPPPO async training)
    for attr in ("_terminate_training_process",):
        if hasattr(controller, attr):
            try:
                getattr(controller, attr)()
            except Exception:
                pass

    return history
