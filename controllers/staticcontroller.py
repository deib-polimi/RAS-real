from .controller import Controller


class StaticController(Controller):
    def __init__(self, period, init_cores, min_cores, max_cores):
        super().__init__(period, init_cores, min_cores, max_cores)

    def control(self, t):
        pass
