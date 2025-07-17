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
    "end" : 1200,
    "noise_start":150, 
    "noise_scale":1.8,
    "noise_type":"avg",
    "generator" : {
        "class" : "TweetGen",
        "params" : {
        	"bias": 40,
            "shift": 10,
        }
    },
    "controller" : {
        "class" : "GPPPOController",
        "params" : {
            "period" : 1, 
            "init_cores" : 1, 
            "min_cores" : 0.5,
            "max_cores" : 28,
            "st" : 1,
            "st_max": 1.0,
            "min_st": 0.5,
            "st_relaxation_factor": 0.005,
            "st_violation_threshold": 0.02,
            "train" : False,
            "burst_mode" : "none",
            "trend_features" : False,
            "enable_log" : True,
            "log_dir" : "./logs",
            "bc": 5.0,
            "dc": 10.0,
            "gp_train_start": 150,
            "gp_min_samples": 500,
            "gp_train_freq": 200,
            "gp_max_buffer_size": 20000,
            "gp_percentile": 95,
            "pi_start_time": 150,
            "gp_time_period": 200
        }
    }
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG) 