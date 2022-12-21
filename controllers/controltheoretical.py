from .controller import Controller

MAX_SCALE_OUT_TIMES = 100

class CTControllerScaleX(Controller):
    def __init__(self, period, init_cores, min_cores, max_cores, BC=0.5, DC=0.95, st=0.8):
        super().__init__(period, init_cores, min_cores, max_cores, st=st)
        self.BC = BC
        self.DC = DC
        self.old_cores = self.init_cores
        self.xc_prec = 0

    def reset(self):
        super().reset()
        self.xc_prec = 0.0

    def control(self, t):
        rt = self.monitoring.getRT()
        if rt == 0:
            return self.init_cores

        e = 1/self.setpoint - 1/rt
        intg = float(self.xc_prec + self.BC * e)
        prop = float(self.DC * e)
        cores = intg + prop
        max_cores = min(self.max_cores, self.old_cores*MAX_SCALE_OUT_TIMES)
        self.cores = float(min(max(cores, self.min_cores), max_cores))
        if t < 20 and self.cores < self.init_cores:
            self.cores = float(self.init_cores)
        self.xc_prec = intg
        self.old_cores = self.cores
        print("cores: ", self.cores, "c_cores", cores, "intg", intg, "prop", prop, "xc_prec", self.xc_prec)

    def __str__(self):
        return super().__str__() + " BC: %.2f DC: %.2f " % (self.BC, self.DC)
