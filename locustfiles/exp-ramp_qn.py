CONFIG = {
    "hosts" : ["http://localhost:8080", "http://localhost:8081"],
    "containerIds" : ["bc4f8d9bdf67", "559cd5c01c6e"],
    "request" : {
        "method" : "POST",
        "data" : {"size": 15000},
        "headers" : {"Content-Type": "application/json"},
        "path" : "/function/graph_bfs"
    },
    "cpu_range_start" : 2,
    "monitoring_window": 1,
    "app_sla": 0.15,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,
    "end" : 240,
    "generator" : {
        "class" : "RampGen",
        "params" : {
            "slope": 0,
            "steady" : 0,
            "initial" : 5
        }
    },
    "controller" : {
        "class" : "OPTCTRL",
        "params" : {
            "period" : 1, 
            "init_cores" : 1, 
            "min_cores" : 0.1,
            "max_cores" : 15,
            "st" :0.8
        }
    }
}

EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)