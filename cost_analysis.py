import json
import os

from generators import *
from scipy.io import loadmat, savemat

import json

def avg_dict(res):
    for k in res:
        res[k] = sum(res[k])/len(res[k])
    
def compare(apps, C_P, comparison):
    for app in apps:
        result_ct = apps[app]["ct"]
        result_qn = apps[app]["qn"]
        comparison[C_P][app] = {}
        for wk in sorted(result_ct.keys()):
            ct = result_ct[wk]
            qn = result_qn[wk]
            res = (ct - qn) / min(ct, qn)
            comparison[C_P][app][wk] = res

comparison = {}
MAX_CP = 10

for C_P in range(1, MAX_CP+1):
    
    comparison[C_P] = {}

    results_graph = {"ct" : {}, "qn" : {}}
    results = {"ct" : {}, "qn" : {}}
    
    for path, dirs, files in os.walk("experiments"):
        if "aws" not in path or not any([x in path for x in ["qn", "ct"]]):
            continue
        with open(f'{path}/config.json', 'r') as f:
            raw = f.read()
            data = json.loads(raw)

        mat=loadmat(f'{path}/data.mat')
        sla = data["app_sla"]
        st = data["controller"]["params"]["st"]
        sla *= st

        total_cost = 0
        C = 1
        P = C * C_P

        for rt, cpu in zip(mat["rts"][0], mat["cores"][0]):
            if rt > sla:
                total_cost += (rt-sla)/sla*P
            else:
                total_cost += (sla-rt)/sla*C
        
        res = results_graph if "graph" in path else results
        res = res["ct"] if "ct" in path else res["qn"]

        app = path.split("exp-")[1].split("_")[0]
        
        res[app] = res.get(app, []) + [total_cost]

    for result in [results, results_graph]:
        for approach in ["qn", "ct"]:
            avg_dict(result[approach])


    res = {"dynamic": results, "graph" : results_graph}

    compare(res, C_P, comparison)


print(json.dumps(comparison, indent=4))

workloads = ["sin", "ramp", "tweet", "wiki"]
workloads_labels = {"ramp" : "RP3", "sin" : "SN3", "tweet": "TW", "wiki": "WK"}
apps = ["dynamic", "graph"]


for app in apps:
    for workload in workloads:
        print(workloads_labels[workload], end="")
        for C_P in range(1, MAX_CP+1):
            print(',{:.2f}'.format(comparison[C_P][app][workload]), end="")
        print("")