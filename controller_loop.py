from locust import events
from locust.runners import WorkerRunner
import gevent
from time import sleep
import docker
from math import floor, ceil

CPU_PERIOD = 100000
cpu_range_start = None
client = docker.from_env()
containerSet = containerQuotas = None
controller = None
end = False

allocatedCoreSet = allocatedCoreQuotas = 0 

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
    shape = environment.shape_class
    sleep(1) # wait for some requests to be executed...
    while not end:
        t = shape.get_run_time()
        cores = controller.tick(t)
        setCores = min(int(cores), controller.max_cores-1)
        quotasCores = max(controller.min_cores, cores-setCores)
        setCores = max(setCores, 1)
        print(f"{controller.name} - t: {int(t)} - cores: {cores} - RT: {controller.monitoring.getRT()} - users: {controller.monitoring.getUsers()}")
        containerSet.update(cpuset_cpus=f"{cpu_range_start}-{cpu_range_start+setCores-1}")
        if cores != setCores:
            containerQuotas.update(cpu_quota=int(quotasCores*CPU_PERIOD), cpu_period=CPU_PERIOD)
        sleep(controller.period)

        
def setup(_controller, containerIds, _cpu_range_start):
    global controller, containerSet, containerQuotas, cpu_range_start
    cpu_range_start = _cpu_range_start
    controller = _controller
    containerSet = client.containers.get(containerIds[0])
    containerQuotas = client.containers.get(containerIds[1])
    containerQuotas.update(cpuset_cpus=f"{cpu_range_start+controller.max_cores-1}")


