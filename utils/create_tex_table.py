import os

graph = False
root_dir = 'experiments'
workloads = ["sin", "ramp", "tweet", "wiki"]
transforms_wl = [("SinGen", "SN3"), ("RampGen", "RP3"), ("TweetGen", "TW2"), ("WikiGen", "WK")]
controllers = ["static", "rule-", "rule3", "step", "target-", "targetfast", "ct"]
transforms_cnt = [ 
    ("StaticController", "Static (1)"), 
    ("RBControllerWithCooldown", "Rule-based"),
    ("RBControllerWithCooldown", "Rule-based (+3)"),
    ("StepController", "Step"),
    ("TargetController", "Target"),
    ("TargetController", "TargetFast"),
    ("CTControllerScaleX", "ScaleX")    
    ] 


res = ""
for workload, transform_wl in zip(workloads, transforms_wl):
    for controller, transform_cnt in zip(controllers, transforms_cnt):
        for root, dirs, files in os.walk(root_dir):
            if workload in root and controller in root and "aws" in root and ("graph" in root if graph else "graph" not in root):
                for file in files:
                    if file.endswith('.tex'):
                        with open(os.path.join(root, file), 'r') as f:
                            res += f.read().replace(*transform_wl).replace(*transform_cnt) + "\n"
                        break
                break

with open("table-dynamic.tex" if not graph else "table-graph.tex", "w") as f:
    f.write(res)
