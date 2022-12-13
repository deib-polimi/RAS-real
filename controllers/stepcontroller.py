import math
from .controller import Controller


class StepController(Controller):
    def __init__(self, period, init_cores, min_cores, max_cores, steps, cooldown=60):
        super().__init__(period, init_cores, min_cores, max_cores)
        self.cooldown = cooldown
        self.steps = steps

    def reset(self):
        super().reset()
        self.nextAction = -1

    def control(self, t):
        if t > self.nextAction:
            cores = self.cores
            self.cores = math.ceil(
                self.cores*self.__getStep__(self.monitoring.getRT()))
            if self.cores != cores:
                self.nextAction = self.cooldown + t
        self.cores = max(min(self.cores, self.max_cores), self.min_cores)


    def __getStep__(self, metric):
        steps = sorted(self.steps.keys())
        for step in steps:
            if step > metric:
                return self.steps[step]
        return self.steps[steps[-1]]

    def __str__(self):
        return super().__str__() + " steps: %s cooldown: %d" % (str(self.steps), self.cooldown)
