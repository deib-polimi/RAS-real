"""B1 MMC-PI always-on · Scenario S15 (StationaryGen λ=18, step, N=1.5) — fast μ̂ (30s).
Necessity completion: physics should reach ~7 cores and recover (~0% viol) where PPO failed (8.5%)."""
from base_experiment import *
from smoke_common import make_config

EXP_NAME = __file__.split("/")[-1].split(".")[0]
setup(EXP_NAME, make_config("S15", "mmcpi"))
