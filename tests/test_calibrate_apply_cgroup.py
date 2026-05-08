"""Acceptance tests for `tools/calibrate_mu.py::_apply_cgroup`.

Covers Docker's CFS quota floor (cpu_quota >= 1000us), state-residue
clearing for integer-`c` calls, and the boundary at the floor itself.

We stub the `docker` module so the test runs even where the SDK is not
installed, and load `calibrate_mu` via importlib to avoid pulling in the
HTTP / numerics path.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


_REPO = Path(__file__).resolve().parents[1]


def _load_calibrate_mu():
    if "docker" not in sys.modules:
        sys.modules["docker"] = types.SimpleNamespace(from_env=lambda: None)
    spec = importlib.util.spec_from_file_location(
        "calibrate_mu", _REPO / "tools" / "calibrate_mu.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def cgroup_env():
    mod = _load_calibrate_mu()
    cset = MagicMock(name="containerSet")
    cquota = MagicMock(name="containerQuotas")
    client = MagicMock()
    client.containers.get.side_effect = lambda name: cset if name == "set" else cquota
    return mod, client, cset, cquota


# -----------------------------------------------------------------------------
# Integer cores → quota must be DISABLED (not silently kept stale)
# -----------------------------------------------------------------------------

def test_integer_cores_disable_quota(cgroup_env):
    mod, client, cset, cquota = cgroup_env
    set_int, quota_frac = mod._apply_cgroup(client, "set", "quota", c=4.0)
    assert (set_int, quota_frac) == (4, 0.0)
    cset.update.assert_called_once_with(cpuset_cpus="0-3")
    cquota.update.assert_called_once_with(cpu_quota=-1)


def test_integer_cores_high(cgroup_env):
    mod, client, cset, cquota = cgroup_env
    mod._apply_cgroup(client, "set", "quota", c=16.0)
    cset.update.assert_called_once_with(cpuset_cpus="0-15")
    cquota.update.assert_called_once_with(cpu_quota=-1)


# -----------------------------------------------------------------------------
# Fractional cores above floor → quota applied
# -----------------------------------------------------------------------------

def test_fractional_cores_apply_quota(cgroup_env):
    mod, client, cset, cquota = cgroup_env
    set_int, quota_frac = mod._apply_cgroup(client, "set", "quota", c=4.7)
    assert set_int == 4
    assert quota_frac == pytest.approx(0.7)
    cset.update.assert_called_once_with(cpuset_cpus="0-3")
    cquota.update.assert_called_once_with(
        cpu_quota=70000, cpu_period=mod.CPU_PERIOD)


def test_quota_at_floor(cgroup_env):
    """Exactly 1000us is allowed by Docker — must apply, not disable."""
    mod, client, cset, cquota = cgroup_env
    mod._apply_cgroup(client, "set", "quota", c=4.01)  # 0.01 * 100000 = 1000
    cquota.update.assert_called_once_with(
        cpu_quota=1000, cpu_period=mod.CPU_PERIOD)


# -----------------------------------------------------------------------------
# Sub-floor fractions → must DISABLE (not invent a sub-1000us quota)
# -----------------------------------------------------------------------------

def test_sub_floor_fraction_disables_quota(cgroup_env):
    mod, client, cset, cquota = cgroup_env
    mod._apply_cgroup(client, "set", "quota", c=4.005)  # 500us < floor
    cquota.update.assert_called_once_with(cpu_quota=-1)


def test_floating_point_noise_treated_as_integer(cgroup_env):
    mod, client, cset, cquota = cgroup_env
    mod._apply_cgroup(client, "set", "quota", c=4.0 + 1e-9)
    cquota.update.assert_called_once_with(cpu_quota=-1)


# -----------------------------------------------------------------------------
# State-residue: two consecutive calls must each carry an explicit quota op
# -----------------------------------------------------------------------------

def test_consecutive_calls_clear_residue(cgroup_env):
    mod, client, cset, cquota = cgroup_env
    # First: fractional → quota applied
    mod._apply_cgroup(client, "set", "quota", c=4.7)
    # Second: integer → quota MUST be cleared, not left at 70000
    mod._apply_cgroup(client, "set", "quota", c=8.0)
    calls = cquota.update.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs == {"cpu_quota": 70000, "cpu_period": mod.CPU_PERIOD}
    assert calls[1].kwargs == {"cpu_quota": -1}


# -----------------------------------------------------------------------------
# cpu_range_start offset
# -----------------------------------------------------------------------------

def test_cpuset_offset(cgroup_env):
    mod, client, cset, cquota = cgroup_env
    mod._apply_cgroup(client, "set", "quota", c=4.0, cpu_range_start=8)
    cset.update.assert_called_once_with(cpuset_cpus="8-11")
