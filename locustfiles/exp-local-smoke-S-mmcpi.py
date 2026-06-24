"""B1 MMC-PI always-on · Scenario S (StationaryGen λ=35, step, N=0.8) — smoke.
Common block from smoke_common.py (fairness by construction)."""
from base_experiment import *
from smoke_common import make_config

EXP_NAME = __file__.split("/")[-1].split(".")[0]
setup(EXP_NAME, make_config("S", "mmcpi"))
