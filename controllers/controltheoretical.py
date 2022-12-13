from .controller import Controller

MAX_SCALE_OUT_TIMES = 3

class CTControllerScaleX(Controller):
    def __init__(self, period, init_cores, min_cores, max_cores, BC=0.5, DC=0.95, st=0.8):
        super().__init__(period, init_cores, min_cores, max_cores, st=st)
        self.BC = BC
        self.DC = DC

    def reset(self):
        super().reset()
        self.xc_prec = 0

    def control(self, t):
        rt = self.monitoring.getRT()
        e = 1/self.setpoint - 1/rt
        xc = float(self.xc_prec + self.BC * e)
        oldcores = self.cores
        self.cores = min(min(max(max(self.min_cores, oldcores/MAX_SCALE_OUT_TIMES), xc + self.DC * e), oldcores*MAX_SCALE_OUT_TIMES), self.max_cores)
        self.xc_prec = float(self.cores - self.BC * e)
    

    def __str__(self):
        return super().__str__() + " BC: %.2f DC: %.2f " % (self.BC, self.DC)
