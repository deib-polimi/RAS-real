CONFIG = {
    "hosts" : ["http://localhost:8080", "http://localhost:8081"],
    "containerIds" : ["dynamic_set", "dynamic_quota"],
    "request" : {
        "method" : "POST",
        "data" : { "username": "dragonbanana", "random_len": 80000},
        "headers" : {"Content-Type": "application/json"},
        "path" : "/function/dynamic_html"
    },
    "cpu_range_start" : 0,
    "monitoring_window": 30,
    "app_sla": 0.25,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,
    "end" : 600,
    "generator" : {
        "class" : "WikiGen",
        "params" : {
        	"bias": 40,
            "shift": 10,
        }
    },
    "controller" : {
        "class" : "RBControllerWithCooldown",
        "params" : {
            "period" : 30, 
            "init_cores" : 1, 
            "min_cores" : 0.5,
            "max_cores" : 16,
            "cooldown" : 0,
            "step" : 3
        }
    }
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)