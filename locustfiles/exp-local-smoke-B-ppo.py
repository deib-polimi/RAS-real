"""B0 PPO-only · Scenario B (bursty/recurring) · N=0.8 — local necessity smoke.
Common block from smoke_common.py (fairness by construction)."""
from base_experiment import *
from smoke_common import make_config

EXP_NAME = __file__.split("/")[-1].split(".")[0]
setup(EXP_NAME, make_config("B", "ppo"))
