"""CalibrationGen — emits a scheduled lam value per time slot.

Pair with CalibrationController using the SAME time slot boundaries (the
two share schedule structure). Used during principled M/M/c calibration.
"""
from .generator import Generator


class CalibrationGen(Generator):
    def __init__(self, schedule):
        """
        Args:
            schedule: list of (t_start_seconds, lam) tuples. The first
                      entry's t_start should be 0. Slots are extended until
                      the next entry's t_start.
        """
        super().__init__()
        if not schedule:
            raise ValueError("CalibrationGen requires non-empty schedule")
        self.schedule = sorted(schedule, key=lambda x: x[0])

    def f(self, x):
        target = self.schedule[0][1]
        for ts, l in self.schedule:
            if x >= ts:
                target = l
        return float(target)

    def __str__(self):
        return super().__str__() + f" schedule={self.schedule}"
