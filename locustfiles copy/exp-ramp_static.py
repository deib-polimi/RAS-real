CONFIG = {

    "host" : "http://localhost:8080",
    "request" : {
        "method" : "POST",
        "data" : { 
            "url": "https://sample-videos.com/img/Sample-jpg-image-50kb.jpg", 
            "width": 10, 
            "height": 10, 
            "n": 30000
        },
        "headers" : {"Content-Type": "application/json"},
        "path" : "/function/'thumbnailer'"
    },
    "containerId" : "25aafb119ae1",
    "monitoring_window": 3,
    "app_sla": 0.4,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,
    "end" : 100,
    "generator" : {
        "class" : "RampGen",
        "params" : {
            "slope": 1,
            "steady" : 50,
            "initial" : 1
        }
    },
    "controller" : {
        "class" : "StaticController",
        "params" : {
            "period" : 1, 
            "init_cores" : 2, 
            "min_cores" : 0.1,
            "max_cores" : 8
        }
    }
}

EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)