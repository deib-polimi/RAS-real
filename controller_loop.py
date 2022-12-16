from locust import events
from locust.runners import WorkerRunner
import gevent
from time import sleep
import docker

CPU_PERIOD = 2000000

client = docker.from_env()
container = None
controller = None
end = False

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
        print(f"{controller.name} - t: {int(t)} - cores: {cores} - RT: {controller.monitoring.getRT()} - users: {controller.monitoring.getUsers()}")
        container.update(cpu_quota=int(cores*CPU_PERIOD), cpu_period=CPU_PERIOD)
        sleep(controller.period)

        

def setup(_controller, containerId):
    global controller, container
    controller = _controller
    container = client.containers.get(containerId)


