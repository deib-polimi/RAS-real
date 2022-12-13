import time
from locust import events
from locust.runners import WorkerRunner

env = None
monitoring = None 
controller = None
method = None
data = None 
headers = None
path = None 

@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    global env
    if not isinstance(environment.runner, WorkerRunner):
        env = environment

def setup(_monitoring, _controller, _method, _headers, _data, _path):
    global monitoring, controller, method, data, path, headers
    monitoring = _monitoring
    controller = _controller
    method = _method
    data = _data
    path = _path
    headers = _headers

def run(task):
    start = time.time()
    if method == "GET":
        task.client.get("")
    elif method == "POST":
        task.client.post(path, json=data, headers=headers)
    end = time.time()

    rt = end - start
    t = env.shape_class.get_run_time()
    users = env.runner.user_count
    controller.cores
    monitoring.tick(t, rt, users, controller.cores)

    




