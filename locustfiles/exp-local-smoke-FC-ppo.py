"""B0 PPO-only · Scenario FC (flash-crowd: load 10→50 @t=300, spawn_rate=50).
Transient probe: does the queue explode before the reactive PPO scales up?"""
from base_experiment import *
from smoke_common import make_config

EXP_NAME = __file__.split("/")[-1].split(".")[0]
setup(EXP_NAME, make_config("FC", "ppo"))
