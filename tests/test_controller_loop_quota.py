"""Acceptance tests for `controller_loop._apply_fractional_quota`.

Mirrors the contract already unit-tested for `tools/calibrate_mu._apply_cgroup`:
Docker rejects cpu_quota below 1000us (CFS minimum), so when the requested
fractional quota falls below the floor we must disable the quota with -1
instead of crashing the gevent greenlet that drives the autoscaler.

We stub `docker` and `gevent` (and friends) so the module loads even on a
machine without the SDK or a Locust runtime.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


_REPO = Path(__file__).resolve().parents[1]


def _stub_locust_environment():
    if "docker" not in sys.modules:
        sys.modules["docker"] = types.SimpleNamespace(from_env=lambda: MagicMock())
    if "gevent" not in sys.modules:
        sys.modules["gevent"] = types.SimpleNamespace(spawn=lambda *a, **k: None)
    if "locust" not in sys.modules:
        sys.modules["locust"] = types.SimpleNamespace(
            events=types.SimpleNamespace(
                init=types.SimpleNamespace(add_listener=lambda f: f),
                test_start=types.SimpleNamespace(add_listener=lambda f: f),
                test_stop=types.SimpleNamespace(add_listener=lambda f: f),
            )
        )
    if "locust.runners" not in sys.modules:
        sys.modules["locust.runners"] = types.SimpleNamespace(WorkerRunner=type("W", (), {}))


def _load_controller_loop():
    _stub_locust_environment()
    spec = importlib.util.spec_from_file_location(
        "controller_loop", _REPO / "controller_loop.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def cl():
    return _load_controller_loop()


# -----------------------------------------------------------------------------
# Above-floor quota → applied verbatim
# -----------------------------------------------------------------------------

def test_fractional_quota_above_floor_applied(cl):
    container = MagicMock()
    cl._apply_fractional_quota(container, 0.5)
    container.update.assert_called_once_with(
        cpu_quota=50000, cpu_period=cl.CPU_PERIOD)


def test_fractional_quota_at_exact_floor(cl):
    """1000us is Docker's hard minimum — must be allowed."""
    container = MagicMock()
    cl._apply_fractional_quota(container, 0.01)  # 0.01 * 100000 = 1000
    container.update.assert_called_once_with(
        cpu_quota=1000, cpu_period=cl.CPU_PERIOD)


# -----------------------------------------------------------------------------
# Sub-floor quota → must DISABLE (not crash the greenlet)
# -----------------------------------------------------------------------------

def test_fractional_quota_below_floor_disables(cl):
    """The crash-causing case: floating-point residual < 1000us."""
    container = MagicMock()
    cl._apply_fractional_quota(container, 0.005)  # 500us
    container.update.assert_called_once_with(cpu_quota=-1)


def test_fractional_quota_zero_disables(cl):
    """min_cores=0 + integer cores produces quotaCores=0 — no crash."""
    container = MagicMock()
    cl._apply_fractional_quota(container, 0.0)
    container.update.assert_called_once_with(cpu_quota=-1)


def test_fractional_quota_floating_point_noise(cl):
    """PPO emits cores like 4.0 + 1e-9; quotaCores is essentially zero."""
    container = MagicMock()
    cl._apply_fractional_quota(container, 1e-9)
    container.update.assert_called_once_with(cpu_quota=-1)


# -----------------------------------------------------------------------------
# Constants exposed
# -----------------------------------------------------------------------------

def test_quota_floor_constant_is_1000us(cl):
    assert cl.QUOTA_FLOOR_US == 1000
    assert cl.CPU_PERIOD == 100000
