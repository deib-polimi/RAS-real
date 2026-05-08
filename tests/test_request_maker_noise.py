"""Acceptance tests for request_maker noise drift and seedable RNG.

Covers Modifica 1 (time-varying noise: step/ramp/bursty) and Modifica 2
(seedable numpy RNG) on request_maker.py.

We re-import the module fresh in each test to reset its module-level state.
"""
from __future__ import annotations

import importlib
import sys
import types

import pytest


def _stub_docker():
    """Stub the optional `docker` SDK so request_maker can be imported in CI."""
    if "docker" not in sys.modules:
        sys.modules["docker"] = types.SimpleNamespace(from_env=lambda: None)


def _fresh_module():
    _stub_docker()
    import request_maker
    importlib.reload(request_maker)
    return request_maker


def _setup_with_drift(rm, *, noise_start, noise_scale, noise_drift_kind,
                     noise_drift_end=None, noise_drift_period=None, seed=None):
    rm.setup(
        _monitoring=None, _controller=None, _hosts=[], _method="POST",
        _headers={}, _data={"size": 1000}, _path="/x",
        _noise_start=noise_start, _noise_scale=noise_scale, _noise_type="avg",
        _noise_drift_kind=noise_drift_kind,
        _noise_drift_end=noise_drift_end,
        _noise_drift_period=noise_drift_period,
        _seed=seed,
    )


# -----------------------------------------------------------------------------
# Modifica 1 — time-varying noise
# -----------------------------------------------------------------------------

def test_noise_scale_at_step_zero_before_start():
    rm = _fresh_module()
    _setup_with_drift(rm, noise_start=300, noise_scale=1.5, noise_drift_kind="step")
    assert rm._noise_scale_at(0) == 0.0
    assert rm._noise_scale_at(299) == 0.0


def test_noise_scale_at_step_full_after_start():
    rm = _fresh_module()
    _setup_with_drift(rm, noise_start=300, noise_scale=1.5, noise_drift_kind="step")
    assert rm._noise_scale_at(300) == pytest.approx(1.5)
    assert rm._noise_scale_at(1000) == pytest.approx(1.5)


def test_noise_scale_at_ramp_linear_interpolation():
    rm = _fresh_module()
    _setup_with_drift(rm, noise_start=100, noise_scale=2.0,
                     noise_drift_kind="ramp", noise_drift_end=200)
    # Before ramp
    assert rm._noise_scale_at(50) == 0.0
    # Start of ramp
    assert rm._noise_scale_at(100) == pytest.approx(0.0, abs=1e-9)
    # Mid-ramp = half of full scale
    assert rm._noise_scale_at(150) == pytest.approx(1.0)
    # End of ramp = full scale
    assert rm._noise_scale_at(200) == pytest.approx(2.0)
    # After ramp = full scale
    assert rm._noise_scale_at(500) == pytest.approx(2.0)


def test_noise_scale_at_bursty_toggles_per_half_period():
    rm = _fresh_module()
    # period=200 => half-period=100; cycles: [0..100)=ON, [100..200)=OFF, ...
    _setup_with_drift(rm, noise_start=0, noise_scale=1.0,
                     noise_drift_kind="bursty", noise_drift_period=200)
    assert rm._noise_scale_at(0) == pytest.approx(0.0)    # cycle 0 -> OFF
    assert rm._noise_scale_at(50) == pytest.approx(0.0)   # still cycle 0
    assert rm._noise_scale_at(100) == pytest.approx(1.0)  # cycle 1 -> ON
    assert rm._noise_scale_at(150) == pytest.approx(1.0)  # still cycle 1
    assert rm._noise_scale_at(200) == pytest.approx(0.0)  # cycle 2 -> OFF
    assert rm._noise_scale_at(300) == pytest.approx(1.0)  # cycle 3 -> ON


def test_noise_scale_at_step_default_when_kind_none():
    """Backward-compat: legacy configs (no noise_drift_kind) behave like step."""
    rm = _fresh_module()
    rm.setup(
        _monitoring=None, _controller=None, _hosts=[], _method="POST",
        _headers={}, _data={"size": 1000}, _path="/x",
        _noise_start=100, _noise_scale=2.0, _noise_type="avg",
    )
    assert rm._noise_scale_at(50) == 0.0
    assert rm._noise_scale_at(100) == pytest.approx(2.0)


# -----------------------------------------------------------------------------
# Modifica 2 — seedable RNG
# -----------------------------------------------------------------------------

def _setup_std_noise(rm, *, seed):
    """noise_type=std exercises the stochastic path (mean=0, stddev>0)."""
    rm.setup(
        _monitoring=None, _controller=None, _hosts=[], _method="POST",
        _headers={}, _data={"size": 1000}, _path="/x",
        _noise_start=0, _noise_scale=1.0, _noise_type="std",
        _noise_drift_kind="step", _seed=seed,
    )


def test_addNoiseToSize_deterministic_with_seed():
    rm1 = _fresh_module()
    _setup_std_noise(rm1, seed=42)
    out1 = [rm1.addNoiseToSize({"size": 1000}, t)["size"] for t in range(10)]

    rm2 = _fresh_module()
    _setup_std_noise(rm2, seed=42)
    out2 = [rm2.addNoiseToSize({"size": 1000}, t)["size"] for t in range(10)]

    assert out1 == out2, "same seed must yield same noise sequence"


def test_addNoiseToSize_different_seeds_diverge():
    rm1 = _fresh_module()
    _setup_std_noise(rm1, seed=1)
    out1 = [rm1.addNoiseToSize({"size": 1000}, t)["size"] for t in range(20)]

    rm2 = _fresh_module()
    _setup_std_noise(rm2, seed=2)
    out2 = [rm2.addNoiseToSize({"size": 1000}, t)["size"] for t in range(20)]

    assert out1 != out2, "different seeds must yield different sequences"


def test_addNoiseToSize_floor_at_100():
    rm = _fresh_module()
    _setup_with_drift(rm, noise_start=0, noise_scale=10.0,
                     noise_drift_kind="step", seed=7)
    # Negative noise can drive size below floor; ensure floor enforced.
    for t in range(50):
        size = rm.addNoiseToSize({"size": 200}, t)["size"]
        assert size >= 100


def test_addNoiseToSize_ramp_grows_over_time():
    """Ramp produces increasing average drift magnitude over the ramp window."""
    rm = _fresh_module()
    _setup_with_drift(rm, noise_start=0, noise_scale=2.0,
                     noise_drift_kind="ramp", noise_drift_end=100, seed=11)
    # Sample many sizes near t=0 and near t=100; the latter should have larger mean.
    early = [rm.addNoiseToSize({"size": 1000}, 1)["size"] for _ in range(200)]
    late = [rm.addNoiseToSize({"size": 1000}, 99)["size"] for _ in range(200)]
    mean_early = sum(early) / len(early)
    mean_late = sum(late) / len(late)
    # noise_type="avg" adds positive bias proportional to scale; mean must grow.
    assert mean_late > mean_early + 100, (mean_early, mean_late)
