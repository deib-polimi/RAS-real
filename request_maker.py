import time
from locust import events
from locust.runners import WorkerRunner

env = None
monitoring = None 
controller = None


@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    global env
    if not isinstance(environment.runner, WorkerRunner):
        env = environment

def setup(_monitoring, _controller):
    global monitoring, controller
    monitoring = _monitoring
    controller = _controller

def run(task):
    start = time.time()
    task.client.get("")
    end = time.time()
    rt = end - start
    t = env.shape_class.get_run_time()
    users = env.runner.user_count
    controller.cores
    monitoring.tick(t, rt, users, controller.cores)

    




