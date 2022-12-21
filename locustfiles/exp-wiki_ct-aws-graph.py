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
    "end" : 250,
    "generator" : {
        "class" : "WikiGen",
        "params" : {
        	"bias": 40,
            "shift": 10,
        }
    },
    "controller" : {
        "class" : "CTControllerScaleX",
        "params" : {
            "period" : 5, 
            "init_cores" : 1, 
            "min_cores" : 0.5,
            "max_cores" : 16,
            "BC" : 0.15, 
            "DC" : 0.15, 
            "st" : 0.7
        }
    }
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
