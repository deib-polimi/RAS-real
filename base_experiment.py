from locust import HttpUser, LoadTestShape, task, between
import request_maker
from generators import *
from controllers import *
from monitoring import Monitoring
import controller_loop
import printer
from locust.runners import WorkerRunner



class UserTask(HttpUser):
    request_maker = None
    @task
    def test(self):
        self.request_maker.run(self)


class Workload(LoadTestShape):
    generator = None
    def tick(self):
        run_time = self.get_run_time()
        if self.end and run_time > self.end:
            return None
        user_count = int(self.generator.tick(run_time))
        return (user_count, self.spawn_rate)


def setup(exp_name, data):
    appSla = data["app_sla"]
    generator = eval(data["generator"]["class"])(**data["generator"]["params"])
    controller = eval(data["controller"]["class"])(**data["controller"]["params"])
    monitoring = Monitoring(data["monitoring_window"], appSla)
    controller.reset()
    monitoring.reset()
    controller.setMonitoring(monitoring)
    controller.setGenerator(generator)
    controller.setSLA(appSla)
    request = data["request"]
    cpu_range_start = data["cpu_range_start"]
    if "noise_start" not in data or "noise_scale" not in data:
        request_maker.setup(monitoring, controller, data["hosts"], request["method"], 
                        request["headers"], request["data"], request["path"])
    else:
        request_maker.setup(monitoring, controller, data["hosts"], request["method"], 
                        request["headers"], request["data"], request["path"],
                        data["noise_start"],data["noise_scale"])
        
    controller_loop.setup(controller, data["containerIds"], cpu_range_start)
    printer.setup(monitoring, generator, controller, exp_name, data)
    
    UserTask.wait_time = between(data["wait_time_min"], data["wait_time_max"])
    UserTask.host = data["hosts"][0]
    UserTask.request_maker = request_maker

    Workload.spawn_rate = data["spawn_rate"]
    Workload.end = data.get("end", None)
    Workload.generator = generator



