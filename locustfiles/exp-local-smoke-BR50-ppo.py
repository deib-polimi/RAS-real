"""B0 PPO-only · Scenario BR50 (bursty μ-drift T=50s, inside feedback dead-band).
Does the pure-feedback PPO fail to track a fast (25s half-period) disturbance?"""
from base_experiment import *
from smoke_common import make_config

EXP_NAME = __file__.split("/")[-1].split(".")[0]
setup(EXP_NAME, make_config("BR50", "ppo"))
