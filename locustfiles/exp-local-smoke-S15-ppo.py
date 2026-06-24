"""B0 PPO-only · Scenario S15 (StationaryGen λ=18, step, N=1.5) — necessity probe.
Strong-but-recoverable drift: does PPO fail despite recovery being feasible (≤7c)?"""
from base_experiment import *
from smoke_common import make_config

EXP_NAME = __file__.split("/")[-1].split(".")[0]
setup(EXP_NAME, make_config("S15", "ppo"))
