CONFIG = {
    "host" : "http://localhost:80",
    "request" : {
        "method" : "GET",
        "data" : { "username": "dragonbanana", "random_len": 1000},
        "headers" : {"Content-Type": "application/json"},
        "path" : "/"
    },
    "containerId" : "8234e4217be4",
    "monitoring_window": 5,
    "app_sla": 0.4,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 10,
    "end" : 100,
    "generator" : {
        "class" : "SinGen",
        "params" : {
        	"period": 25,
            "mod": 50,
            "shift": 150
        }
    },
    "controller" : {
        "class" : "CTControllerScaleX",
        "params" : {
            "period" : 1, 
            "init_cores" : 0.5, 
            "min_cores" : 0.5,
            "max_cores" : 4,
            "BC" : 0.3, 
            "DC" : 0.5, 
            "st" : 0.8
        }
    }
}

EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)