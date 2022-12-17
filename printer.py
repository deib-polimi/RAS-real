from numpy import array
from scipy.io import savemat
import matplotlib.pyplot as plt
import time
import os
from locust import events
from locust.runners import WorkerRunner

monitoring = None
generator = None 
controller = None 
name = None 

id = int(time.time()*1000)
output_path = None


@events.test_stop.add_listener
def on_locust_stop(environment, **_kwargs):
    if not isinstance(environment.runner, WorkerRunner):
        logTeX()
        plot()
        saveMat()
        

def saveMat():
    arts = array(monitoring.getAllRTs())
    acores = array(monitoring.getAllCores())
    aviolations = monitoring.getViolations()
    atimes = monitoring.getAllTimes()
    if not isinstance(aviolations, list):
        arts = [arts]
        acores = [acores]
        aviolations = [aviolations]
        atimes = [atimes]

    for (time, rts, cores, violations) in zip(atimes, arts, acores, aviolations):
        mdic = {"time": time, "rts": rts,"cores":cores,"violations":violations}    
        savemat(f"{output_path}/data.mat", mdic)

def logTeX():
        arts = array(monitoring.getAllRTs())
        acores = array(monitoring.getAllCores())
        aviolations = monitoring.getViolations()
        if not isinstance(aviolations, list):
            arts = [arts]
            acores = [acores]
            aviolations = [aviolations]

        output = ""
        for (rts, cores, violations) in zip(arts, acores, aviolations):
            output += "\\textit{%s} & \\textit{%s} & $%.2f$ & $%.2f$ & $%.2f$ & $%.2f$ & $%d$ & $%.2f$ \\\\ \hline \n" % (controller.name, generator.name, rts.mean(), rts.std(), rts.min(), rts.max(), violations, cores.mean())
        
        with open(f"{output_path}/data.tex", "w") as f:
           f.write(output)

def plot():
    i = 0
    arts = array(monitoring.getAllRTs())
    acores = array(monitoring.getAllCores())
    aviolations = monitoring.getViolations()
    ausers = monitoring.getAllUsers()
    atimes = monitoring.getAllTimes()
    if not isinstance(aviolations, list):
        arts = [arts]
        acores = [acores]
        aviolations = [aviolations]
        ausers = [ausers]
    for (rts, cores, users) in zip(arts, acores, ausers):
        fig, ax1 = plt.subplots()
        ax1.set_ylabel('# workload')
        ax1.set_xlabel("time [s]")
        ax1.plot(atimes, users, 'r--', linewidth=2)
        ax2 = ax1.twinx()
        ax2.plot(atimes, cores, 'b-', linewidth=2)
        ax2.set_ylabel('# cores')
        fig.tight_layout()
        plt.savefig(f"{output_path}/workcore.pdf")
        plt.close()

        fig, ax1 = plt.subplots()
        ax1.set_ylabel('RT [s]')
        ax1.set_xlabel("time [s]")
        ax1.plot(atimes, rts, 'g-', linewidth=2)
        ax2 = ax1.twinx()
        sla = monitoring.sla[i] if isinstance(monitoring.sla, list) else monitoring.sla
        ax2.plot(atimes, [sla] * len(rts),
                'r--', linewidth=2)
        ax2.set_ylabel('RT [s]')
        m1, M1 = ax1.get_ylim()
        m2, M2 = ax2.get_ylim()
        m = min([m1, m2])
        M = max([M1, M2])
        ax1.set_ylim([m, M])
        ax2.set_ylim([m, M])
        fig.tight_layout()
        plt.savefig(f"{output_path}/rt.pdf")
        plt.close()
        i += 1


def setup(_monitoring, _generator, _controller, _name):
    global monitoring, generator, controller, name, output_path
    monitoring = _monitoring
    generator = _generator
    controller = _controller
    name = _name
    output_path = f"experiments/results/{name}-{id}"
    if not os.path.exists(output_path):
        os.makedirs(output_path)
