from numpy import array
from scipy.io import savemat
import matplotlib.pyplot as plt

from locust import events
from locust.runners import WorkerRunner

monitoring = None
generator = None 
controller = None 
name = None 

output_path = "experiments/results/"

@events.test_stop.add_listener
def on_locust_stop(environment, **_kwargs):
    if not isinstance(environment.runner, WorkerRunner):
        with open(f"{output_path}{name}.tex", "w") as f:
           f.write(log())
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
        savemat("%s%s_%s.mat"%(output_path,controller.name,generator.name), mdic)

def log():
        arts = array(monitoring.getAllRTs())
        acores = array(monitoring.getAllCores())
        aviolations = monitoring.getViolations()
        if not isinstance(aviolations, list):
            arts = [arts]
            acores = [acores]
            aviolations = [aviolations]

        output = ""
        for (rts, cores, violations) in zip(arts, acores, aviolations):
            output += "\\textit{%s} & \\textit{%s} & $%.2f$ & $%.2f$ & $%.2f$ & $%.2f$ & $%d$ & $%2f$ \\\\ \hline \n" % (controller.name, generator.name, rts.mean(), rts.std(), rts.min(), rts.max(), violations, cores.mean())
        return output

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
        print(atimes, users)
        ax1.plot(atimes, users, 'r--', linewidth=2)
        ax2 = ax1.twinx()
        ax2.plot(atimes, cores, 'b-', linewidth=2)
        ax2.set_ylabel('# cores')
        fig.tight_layout()
        plt.savefig(f"{output_path}/{name}-{i}-workcore.pdf")
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
        plt.savefig(f"{output_path}/{name}-{i}-rt.pdf")
        plt.close()
        i += 1


def setup(_monitoring, _generator, _controller, _name):
    global monitoring, generator, controller, name
    monitoring = _monitoring
    generator = _generator
    controller = _controller
    name = _name
