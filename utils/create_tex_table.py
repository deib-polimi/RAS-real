import os
import sys

graph = sys.argv[1] == "True"
root_dir = 'experiments'
workloads = ["sin", "ramp", "tweet", "wiki"]
transforms_wl = [("SinGen", "SN3"), ("RampGen", "RP3"), ("TweetGen", "TW2"), ("WikiGen", "WK")]
controllers = ["static", "rule-", "rule3", "step", "target-", "targetfast", "ct", "qn"]
transforms_cnt = [ 
    ("StaticController", "Static (1)"), 
    ("RBControllerWithCooldown", "Rule-based"),
    ("RBControllerWithCooldown", "Rule-based (+3)"),
    ("StepController", "Step"),
    ("TargetController", "Target"),
    ("TargetController", "TargetFast"),
    ("CTControllerScaleX", "\\approachCT"),
    ("OPTCTRL", "\\approachOPT")    
    ] 


res = ""
for workload, transform_wl in zip(workloads, transforms_wl):
    for controller, transform_cnt in zip(controllers, transforms_cnt):
        values = []
        prefix = ""
        postfix = ""
        last = controller == controllers[-1]
        for root, dirs, files in os.walk(root_dir):
            if workload in root and controller in root and "aws" in root and ("graph" in root if graph else "graph" not in root):
                for file in files:
                    if file.endswith('.tex'):
                        with open(os.path.join(root, file), 'r') as f:
                            data = f.read().split('&')
                            data[-1] = data[-1].split('\\\\')[0]
                            values.append([float(x.strip().replace('$', '')) for x in data[2:] if x.strip()])
                            if not prefix:
                                data[0], data[1] = data[1], data[0]
                                if last:
                                    data[0] = f"\multirow{{-{len(controllers)}}}{{*}}{{{data[0]}}}"
                                else:
                                    data [0] = ""
                                prefix = ' & '.join(data[0:2]).replace(*transform_wl).replace(*transform_cnt) + ' & '  
                            if not postfix:
                                postfix = "\\\\"
                                if last:
                                    postfix += " \hline"
                                                           
                        break
        average_values = [sum(x)/len(x) for x in zip(*values)]
        average_values[4] = int(average_values[4])
        formatted_values = ['{:.2f}'.format(x) if isinstance(x, float) else str(x) for x in average_values]        
        res += prefix +' & '.join(formatted_values) + postfix + "\n"

with open("table-dynamic.tex" if not graph else "table-graph.tex", "w") as f:
    f.write(res)
