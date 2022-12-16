import time
from locust import events
from locust.runners import WorkerRunner
from random import random
import controller_loop

env = None
monitoring = None 
controller = None
method = None
data = None 
headers = None
path = None 
hosts = None

@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    global env
    if not isinstance(environment.runner, WorkerRunner):
        env = environment

def setup(_monitoring, _controller, _hosts, _method, _headers, _data, _path):
    global monitoring, controller, hosts, method, data, path, headers
    monitoring = _monitoring
    controller = _controller
    hosts = _hosts
    method = _method
    data = _data
    path = _path
    headers = _headers

def run(task):
    cores = controller.cores
    if cores < 1:
        host = hosts[1]
    else:
        c1 = controller_loop.setCores
        c2 = controller_loop.quotaCores
        p = c1/(c1+c2)
        host = hosts[0] if random() <= p else hosts[1]

    start = time.time()
    if method == "GET":
        task.client.get(host+path)
    elif method == "POST":
        task.client.post(host+path, json=data, headers=headers)
    end = time.time()

    rt = end - start
    t = env.shape_class.get_run_time()
    users = env.runner.user_count
    
    monitoring.tick(t, rt, users, cores)

    




