CONFIG = {
    "host" : "http://localhost:8080",
    "request" : {
        "method" : "POST",
        "data" : { "username": "dragonbanana", "random_len": 80000},
        "headers" : {"Content-Type": "application/json"},
        "path" : "/function/dynamic_html"
    },
    "containerId" : "296d96102c25",
    "monitoring_window": 1,
    "app_sla": 0.4,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,
    "end" : 600,
    "generator" : {
        "class" : "SinGen",
        "params" : {
        	"period":300,
            "mod":30,
            "shift":42
        }
    },
    "controller" : {
        "class" : "OPTCTRL",
        "params" : {
            "period" : 1, 
            "init_cores" : 1, 
            "min_cores" : 0.1,
            "max_cores" : 30,
            "st" :0.8
        }
        
    }
}

EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)