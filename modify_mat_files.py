import json
import os

from generators import *
from scipy.io import loadmat, savemat



for path, dirs, files in os.walk("experiments"):
    if "aws" not in path:
        continue
    with open(f'{path}/config.json', 'r') as f:
        raw = f.read()
        data = json.loads(raw)

    generator = eval(data["generator"]["class"])(**data["generator"]["params"])

    mat=loadmat(f'{path}/data.mat')
    time = mat['time'][0]
    workload = []
    for t in time:
        workload.append(generator.tick(t))
    mat['workload'] = [workload]
    savemat(f'{path}/data.mat', mat)



