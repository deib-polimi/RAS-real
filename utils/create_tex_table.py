import os
import sys
import argparse
import re
from pathlib import Path

global graph, root_dir, outfile

def parse_args():
    parser = argparse.ArgumentParser(description='Parse command line arguments.')
    parser.add_argument('--graph', action='store_true', help='Boolean flag to indicate if graph is enabled')
    parser.add_argument('--root_dir', type=str, required=True, help='Path to the root directory')
    parser.add_argument('--outfile', type=str, required=True, help='Path to the output file')
    
    args = parser.parse_args()
    return args.graph, args.root_dir, args.outfile

def get_workloads_and_controllers(root_dir):
    workloads = set()
    controllers = set()
    pattern = re.compile(r'exp-(?P<workload>[^_]+)_(?P<ctrl>[^-]+)-aws-graph-\d+')

    for filename in os.listdir(root_dir):
        match = pattern.match(filename)
        if match:
            workloads.add(match.group('workload'))
            controllers.add(match.group('ctrl'))

    return sorted(list(workloads)), sorted(list(controllers))

# Define a function to replace only full words
def replace_full_words(text, replacements):
    for old, new in replacements.items():
        text = re.sub(rf'\b{re.escape(old)}\b', new, text)
    return text

graph, root_dir, outfile = parse_args()
workloads, controllers = get_workloads_and_controllers(root_dir)
print("Workloads:", workloads)
print("Controllers:", controllers)

#graph = sys.argv[1] == "True"
#root_dir = './experiments/robust_exp2/'
#workloads = ["sin"]
transforms_wl = {"SinGen": "SN3", "RampGen":"RP3", "TweetGen":"TW2","WikiGen":"WK"}
#controllers = ["static", "rule-", "rule3", "step", "target-", "targetfast", "ct", "qn"]
#controllers = ["ct", "qn","robust"]
# transforms_cnt = [ 
#     ("StaticController", "Static (1)"), 
#     ("RBControllerWithCooldown", "Rule-based"),
#     ("RBControllerWithCooldown", "Rule-based (+3)"),
#     ("StepController", "Step"),
#     ("TargetController", "Target"),
#     ("TargetController", "TargetFast"),
#     ("CTControllerScaleX", "\\approachCT"),
#     ("OPTCTRL", "\\approachOPT")    
#     ] 

transforms_cnt = { 
    "CTControllerScaleX":"\\\\approachCT",
    "OPTCTRL":"\\\\approachOPT",
    "OPTCTRLROBUST":"ROBUST"    
}


res = ""
for workload, transform_wl in zip(workloads, transforms_wl):
    for controller, transform_cnt in zip(controllers, transforms_cnt):
        values = []
        prefix = ""
        postfix = ""
        last = controller == controllers[-1]
        for root, dirs, files in os.walk(root_dir):
            if f"{workload}_{controller}" in root and "aws" in root and ("graph" in root if graph else "graph" not in root):
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

                                prefix=replace_full_words(' & '.join(data[0:2]), transforms_wl)
                                prefix=replace_full_words(prefix, transforms_cnt)+' & '
                                #prefix = ' & '.join(data[0:2]).replace(*transform_wl).replace(*transform_cnt) + ' & '  
                            if not postfix:
                                postfix = "\\\\"
                                if last:
                                    postfix += " \hline"
                        break

        average_values = [sum(x)/len(x) for x in zip(*values)]
        average_values[4] = int(average_values[4])
        formatted_values = ['{:.2f}'.format(x) if isinstance(x, float) else str(x) for x in average_values]        
        res += prefix +' & '.join(formatted_values) + postfix + "\n"

Path(outfile).write_text(res)

