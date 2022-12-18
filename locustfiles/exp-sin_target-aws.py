appSLA = 0.25

CONFIG = {
    "hosts" : ["http://localhost:8080", "http://localhost:8081"],
    "containerIds" : ["cf4390cdcb2d", "e5aed9e83503"],
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
        "class" : "SinGen",
        "params" : {
        	"period": 200,
            "mod": 20,
            "shift": 20
        }
    },
    "controller" : {
        "class" : "TargetController",
        "params" : {
            "period" : 30, 
            "init_cores" : 1, 
            "min_cores" : 0.5,
            "max_cores" : 16,
            "cooldown" : 0
        }
    }
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)