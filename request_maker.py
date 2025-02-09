import time
from locust import events
from locust.runners import WorkerRunner
from random import random, gauss
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

@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    global env
    if not isinstance(environment.runner, WorkerRunner):
        env = environment

def setup(_monitoring, _controller, _hosts, _method, _headers, _data, _path,_noise_start,_noise_scale):
    global monitoring, controller, hosts, method, data, path, headers, noise_start, noise_scale
    monitoring = _monitoring
    controller = _controller
    hosts = _hosts
    method = _method
    data = _data
    path = _path
    headers = _headers
    noise_start = _noise_start
    noise_scale = _noise_scale

def addNoiseToSize(data, t):
    if t >= noise_start:
        original_size = data["size"]
        noise = gauss(0, original_size * noise_scale)
        data["size"] += noise
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
        p = c1/(c1+c2)
        host = hosts[0] if random() <= p else hosts[1]
    
    t = env.shape_class.get_run_time()

    start = time.time()
    if method == "GET":
        task.client.get(host+path)
    elif method == "POST":
        #task.client.post(host+path, json=data, headers=headers)

        json_data = data.copy()
        json_data = addNoiseToSize(json_data, t)
        task.client.post(host + path, json=json_data, headers=headers)
    end = time.time()

    rt = end - start
    users = env.runner.user_count
    
    monitoring.tick(t, rt, users, cores)

    




