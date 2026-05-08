from .generator import Generator


class StationaryGen(Generator):
    """Constant-load generator: always returns `lam` users (used for μ-drift studies)."""

    def __init__(self, lam):
        super().__init__()
        self.lam = lam

    def f(self, x):
        return self.lam

    def __str__(self):
        return super().__str__() + " lam: %s" % (self.lam,)
