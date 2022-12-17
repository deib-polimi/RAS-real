CONFIG = {
    "hosts" : ["http://localhost:8080", "http://localhost:8081"],
    "containerIds" : ["20e2d5004d48", "9b5431de6ba9"],
    "request" : {
        "method" : "POST",
        "data" : {"size": 15000},
        "headers" : {"Content-Type": "application/json"},
        "path" : "/function/graph_bfs"
    },
    "cpu_range_start" : 2,
    "monitoring_window": 30,
    "app_sla": 0.15,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,
    "end" : 240,
    "generator" : {
        "class" : "RampGen",
        "params" : {
            "slope": 0.25,
            "steady" : 120,
            "initial" : 1
        }
    },
    "controller" : {
        "class" : "CTControllerScaleX",
        "params" : {
            "period" : 5, 
            "init_cores" : 1, 
            "min_cores" : 1.0,
            "max_cores" : 15,
            "BC" : 25, 
            "DC" : 50, 
            "st" :0.8
        }
    }
}

EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)