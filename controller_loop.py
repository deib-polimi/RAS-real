from locust import events
from locust.runners import WorkerRunner
import gevent
from time import sleep
import docker
from math import floor, ceil

CPU_PERIOD = 100000
QUOTA_FLOOR_US = 1000   # Docker rejects cpu_quota < 1000us (CFS minimum)
cpu_range_start = None

client = docker.from_env()

containerSet = containerQuotas = None
controller = None
end = False

setCores = quotaCores = None


def _apply_fractional_quota(container, quota_cores, cpu_period=CPU_PERIOD):
    """Apply cpu_quota to `container` while respecting Docker's CFS floor.

    Docker's update API rejects `cpu_quota` values below 1000us with
    400 Bad Request ("CPU cfs quota can not be less than 1ms"). When the
    requested fractional quota falls under the floor — which can happen
    with `min_cores=0.0` plus floating-point residuals in `cores` — we
    disable the quota with `cpu_quota=-1` instead of letting the greenlet
    crash. Routing in `request_maker` already directs ~all traffic to the
    set container in this regime, so the disabled quota is harmless.
    """
    quota_us = int(quota_cores * cpu_period)
    if quota_us >= QUOTA_FLOOR_US:
        container.update(cpu_quota=quota_us, cpu_period=cpu_period)
    else:
        container.update(cpu_quota=-1)


@events.test_start.add_listener
def on_locust_start(environment, **_kwargs):
    if not isinstance(environment.runner, WorkerRunner):
        gevent.spawn(controller_loop, environment)


@events.test_stop.add_listener
def on_locust_start(environment, **_kwargs):
    global end
    if not isinstance(environment.runner, WorkerRunner):
        end = True

def controller_loop(environment):
    global setCores, quotaCores
    shape = environment.shape_class
    sleep(1) # wait for some requests to be executed...
    while not end:
        t = shape.get_run_time()
        cores = controller.tick(t)
        setCores = min(int(cores), controller.max_cores-1)
        quotaCores = max(controller.min_cores, cores-setCores)
        setCores = max(setCores, 1)
        print(f"{controller.name} - t: {int(t)} - cores: {cores} - RT: {controller.monitoring.getRT()} - users: {controller.monitoring.getUsers()}")
        containerSet.update(cpuset_cpus=f"{cpu_range_start}-{cpu_range_start+setCores-1}")
        if cores != setCores:
            _apply_fractional_quota(containerQuotas, quotaCores)
        sleep(controller.period)


def setup(_controller, containerIds, _cpu_range_start):
    global controller, containerSet, containerQuotas, cpu_range_start, setCores, quotaCores
    cpu_range_start = _cpu_range_start
    controller = _controller
    containerSet = client.containers.get(containerIds[0])
    containerQuotas = client.containers.get(containerIds[1])
    # Reset any residual cpu_quota left by previous tools (e.g. calibrate_mu
    # may have set cpu_quota=-1 or a finite value; we want a clean slate).
    containerQuotas.update(
        cpuset_cpus=f"{cpu_range_start+controller.max_cores-1}",
        cpu_quota=-1,
    )
    setCores = 1
    quotaCores = min(1, controller.min_cores)
