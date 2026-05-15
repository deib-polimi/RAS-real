import random
from .generator import Generator


class DistributionGen(Generator):
    """Training-on-distribution wrapper: resamples lam ~ U([lam_min, lam_max])
    at the start of every episode of length `episode_len` seconds.

    Used to train data-driven controllers (PPO etc.) on a distribution of
    workloads rather than a single fixed point, so that 'OOD' is well-defined
    (anything outside [lam_min, lam_max] or with drift never seen in training).
    """

    def __init__(self, lam_min, lam_max, episode_len=300, seed=None):
        super().__init__()
        self.lam_min = float(lam_min)
        self.lam_max = float(lam_max)
        self.episode_len = float(episode_len)
        self.rng = random.Random(seed)
        self._cur_episode = -1
        self._cur_lam = self.rng.uniform(self.lam_min, self.lam_max)

    def f(self, x):
        ep = int(x // self.episode_len)
        if ep != self._cur_episode:
            self._cur_episode = ep
            self._cur_lam = self.rng.uniform(self.lam_min, self.lam_max)
        return self._cur_lam

    def __str__(self):
        return super().__str__() + (
            f" lam~U([{self.lam_min},{self.lam_max}]) ep={self.episode_len}s"
        )
