class Controller:
    def __init__(self, period, init_cores, min_cores, max_cores, st=0.8):
        self.period = period
        self.init_cores = init_cores
        self.st = st
        self.lastT = -1
        self.name = type(self).__name__
        self.cores = init_cores
        self.min_cores = min_cores
        self.max_cores = max_cores

    def setName(self, name):
        self.name = name

    def setSLA(self, sla):
        self.sla = sla
        self.setpoint = sla*self.st

    def setMonitoring(self, monitoring):
        self.monitoring = monitoring
    
    def setGenerator(self, generator):
        self.generator = generator

    def tick(self, t):
        if not t:
            self.reset()
        if t and t - self.lastT > self.period:
            self.lastT = t
            self.control(t)
            
        return self.cores

    def control(self, t):
        pass

    def reset(self):
        self.cores = self.init_cores

    def __str__(self):
        return "%s - period: %d init_cores: %.2f" % (self.name, self.period, self.init_cores)
