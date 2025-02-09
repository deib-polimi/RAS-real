CONFIG = {
    "hosts" : ["http://localhost:8080", "http://localhost:8081"],
    "containerIds" : ["graph_set", "graph_quota"],
    "request" : {
        "method" : "POST",
        "data" : { "size" : 25000 },
        "headers" : {"Content-Type": "application/json"},
        "path" : "/function/graph_mst"
    },
    "cpu_range_start" : 0,
    "monitoring_window": 30,
    "app_sla": 0.25,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,
    "end" : 600,
    "noise_start":300,
    "noise_scale":2.0,
    "generator" : {
        "class" : "RampGen",
        "params" : {
            "slope": 0.15,
            "steady" : 450,
            "initial" : 10,
            "rampstart" : 150
        }
    },
    "controller" : {
        "class" : "OPTCTRL",
        "params" : {
            "period" : 1, 
            "init_cores" : 1, 
            "min_cores" : 0.5,
            "max_cores" : 16,
            "st" : 0.8
        }
    }
}

EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
