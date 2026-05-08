import time
from locust import events
from locust.runners import WorkerRunner
from random import random
import numpy as np
import controller_loop

env = None
monitoring = None
controller = None
method = None
data = None
headers = None
path = None
hosts = None
noise_start = None
noise_scale = None
noise_type = None
noise_drift_kind = None
noise_drift_end = None
noise_drift_period = None
_rng = None


@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    global env
    if not isinstance(environment.runner, WorkerRunner):
        env = environment


def setup(_monitoring, _controller, _hosts, _method, _headers, _data, _path,
          _noise_start=-1, _noise_scale=0, _noise_type="std",
          _noise_drift_kind="step", _noise_drift_end=None,
          _noise_drift_period=None, _seed=None):
    global monitoring, controller, hosts, method, data, path, headers
    global noise_start, noise_scale, noise_type
    global noise_drift_kind, noise_drift_end, noise_drift_period
    global _rng
    monitoring = _monitoring
    controller = _controller
    hosts = _hosts
    method = _method
    data = _data
    path = _path
    headers = _headers
    noise_start = _noise_start
    noise_scale = _noise_scale
    noise_type = _noise_type
    noise_drift_kind = _noise_drift_kind or "step"
    noise_drift_end = _noise_drift_end
    noise_drift_period = _noise_drift_period
    _rng = np.random.default_rng(_seed)


def _noise_scale_at(t):
    """Return the active noise scale at time t given the configured drift profile."""
    if noise_start is None or noise_start < 0 or t < noise_start:
        return 0.0

    kind = noise_drift_kind or "step"

    if kind == "step":
        return float(noise_scale)

    if kind == "ramp":
        end = noise_drift_end if noise_drift_end is not None else noise_start
        if end <= noise_start:
            return float(noise_scale)
        if t >= end:
            return float(noise_scale)
        frac = (t - noise_start) / (end - noise_start)
        return float(noise_scale) * frac

    if kind == "bursty":
        period = noise_drift_period if noise_drift_period and noise_drift_period > 0 else 1.0
        half = period / 2.0
        cycle = int((t - noise_start) // half)
        return float(noise_scale) if (cycle % 2 == 1) else 0.0

    return 0.0


def addNoiseToSize(data, t):
    scale = _noise_scale_at(t)
    if scale == 0.0:
        return data
    original_size = data["size"]

    if noise_type == "std":
        noise = _rng.normal(0, original_size * 2 * scale)
    elif noise_type == "avg":
        noise = _rng.normal(original_size * scale, 0)
    elif noise_type == "all":
        noise = _rng.normal(original_size * scale, original_size * 2 * scale)
    else:
        noise = 0

    data["size"] += int(noise)
    if data["size"] < 100:
        data["size"] = 100
    return data


def run(task):
    cores = controller.cores
    if cores < 1:
        host = hosts[1]
    else:
        c1 = controller_loop.setCores
        c2 = controller_loop.quotaCores
        p = c1 / (c1 + c2)
        host = hosts[0] if random() <= p else hosts[1]

    t = env.shape_class.get_run_time()

    start = time.time()
    if method == "GET":
        task.client.get(host + path)
    elif method == "POST":
        json_data = data.copy()
        json_data = addNoiseToSize(json_data, t)
        task.client.post(host + path, json=json_data, headers=headers)
    end = time.time()

    rt = end - start
    users = env.runner.user_count

    monitoring.tick(t, rt, users, cores)
