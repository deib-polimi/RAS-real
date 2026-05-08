"""Tests for the GP async-training queue contract (A+B fix).

Documents the deadlock observed in run 3a (commit 975884c logs):
when the pickled GP model exceeds Linux's pipe buffer (~64KB), `mp.Queue.put()`
returns synchronously but the subprocess can NOT exit until the parent drains
the pipe. Gating the parent's `queue.get()` on `is_alive()` therefore creates
a circular wait — the deadlock cause.

Two tests:

1. `test_mp_queue_large_payload_blocks_subprocess`
   OS-invariant: reproduces the deadlock condition. Always passes — proves
   that our fix's premise (drain queue regardless of `is_alive()`) is needed.

2. `test_worker_writes_model_to_disk_path`
   Contract test for B-fix: the worker must pickle to disk and put only the
   path string on the queue (small, fits in pipe). Skipped without torch.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import pickle
import sys
import tempfile
import time

import numpy as np
import pytest


# -----------------------------------------------------------------------------
# OS-invariant test (runs anywhere — documents the bug)
# -----------------------------------------------------------------------------

def _large_put_worker(q, payload):
    q.put(("success", payload, 1))


def test_mp_queue_large_payload_blocks_subprocess():
    """Linux pipe buffer is ~64KB. mp.Queue's feeder thread blocks the
    subprocess from exiting until the parent drains the pipe.

    This test reproduces the EXACT condition observed in run 3a at t=102:
    `[GP-WORKER] PUT_QUEUE` fires, but the subprocess stays `alive=True`
    until something reads the queue. Our fix (A) reads the queue without
    gating on `is_alive()`, breaking the circular wait.
    """
    q = mp.Queue()
    big = b"x" * 100_000  # > 64KB pipe buffer

    p = mp.Process(target=_large_put_worker, args=(q, big))
    p.start()

    # Give put() time to enqueue + feeder time to fill the pipe and block.
    time.sleep(0.5)

    # The bug condition: data is in flight but subprocess is "alive".
    assert p.is_alive(), \
        "expected subprocess to be alive (feeder thread blocked on pipe)"

    # Fix premise: parent drains queue → feeder unblocks → subprocess exits.
    result = q.get(timeout=2.0)
    assert result[0] == "success"
    assert len(result[1]) == 100_000

    # After draining, subprocess can finally exit.
    p.join(timeout=3.0)
    assert not p.is_alive(), \
        "subprocess should have exited after queue drain"


# -----------------------------------------------------------------------------
# Contract test for B-fix (skipped without torch)
# -----------------------------------------------------------------------------

@pytest.fixture
def gpppo_worker():
    pytest.importorskip("torch")  # GPPPOController parent imports torch
    from controllers.gpppo_controller import _train_gp_worker_process
    return _train_gp_worker_process


def test_worker_writes_model_to_disk_path(gpppo_worker, tmp_path):
    """B-fix contract: worker pickles model to `model_path`, puts ONLY the
    path string on the queue. The string is short (path < 1KB) so it never
    exceeds the pipe buffer, regardless of the model size.
    """
    # Minimal training data — enough to fit a real GP
    rng = np.random.default_rng(42)
    training_data = [
        (rng.normal(size=5), float(rng.normal()))
        for _ in range(30)
    ]
    q = mp.Queue()
    model_path = str(tmp_path / "test-gpr.pkl")

    # Run worker inline (no subprocess — just verify contract)
    gpppo_worker(training_data, q, normalize_inputs=False, model_path=model_path)

    # Queue payload is (status, path_string, num_samples) — NOT bytes
    result = q.get(timeout=2.0)
    status, payload, n = result
    assert status == "success", f"got status={status} payload={payload!r}"
    assert isinstance(payload, str), \
        f"queue payload must be a path string (B-fix), got {type(payload).__name__}"
    assert payload == model_path
    assert os.path.exists(payload), "worker did not write model to the given path"

    # File on disk must be the pickled (scaler, gpr) tuple
    with open(payload, "rb") as f:
        loaded = pickle.load(f)
    assert isinstance(loaded, tuple) and len(loaded) == 2
    scaler, gpr = loaded
    assert scaler is None  # normalize_inputs=False
    assert gpr is not None

    # Sanity: queue payload (path) is well under pipe-buffer limit
    encoded_size = len(pickle.dumps(("success", payload, n)))
    assert encoded_size < 4096, \
        f"queue payload should be tiny after B-fix, got {encoded_size} bytes"


def test_worker_with_normalize_inputs_pickles_scaler(gpppo_worker, tmp_path):
    """B-fix preserves the (scaler, gpr) tuple semantics when normalize_inputs=True."""
    rng = np.random.default_rng(7)
    training_data = [
        (rng.normal(size=5), float(rng.normal()))
        for _ in range(30)
    ]
    q = mp.Queue()
    model_path = str(tmp_path / "scaler-gpr.pkl")

    gpppo_worker(training_data, q, normalize_inputs=True, model_path=model_path)

    status, payload, _ = q.get(timeout=2.0)
    assert status == "success"
    with open(payload, "rb") as f:
        scaler, gpr = pickle.load(f)
    assert scaler is not None, "scaler must be pickled when normalize_inputs=True"
    assert gpr is not None
