from locust import HttpUser, LoadTestShape, task, between
import json
import request_maker
from generators import *
from controllers import *
from monitoring import Monitoring
import controller_loop
import printer
from locust import events
from locust.runners import WorkerRunner


EXP_FILE = "experiments/config/exp-ramp_ct-aws.json"

with open(EXP_FILE) as f:
    data = json.load(f)

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
request_maker.setup(monitoring, controller, data["hosts"], request["method"], request["headers"], request["data"], request["path"])
controller_loop.setup(controller, data["containerIds"], cpu_range_start)
printer.setup(monitoring, generator, controller, EXP_FILE.split("/")[-1].replace(".json", ""))


class UserTask(HttpUser):
    wait_time = between(data["wait_time_min"], data["wait_time_max"])
    host = data["hosts"][0]
    @task
    def test(self):
        request_maker.run(self)


class Worload(LoadTestShape):
    spawn_rate = data["spawn_rate"]
    end = data.get("end", None)

    def tick(self):
        run_time = self.get_run_time()
        if self.end and run_time > self.end:
            return None
        user_count = int(generator.tick(run_time))
        return (user_count, self.spawn_rate)

