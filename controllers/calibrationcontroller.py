"""CalibrationController — applies a fixed cores value per schedule slot.

Used to perform calibration of μ_eff/core via Operational Utilization Law
through the SAME request path used by experiments (Locust + request_maker
+ monitoring), eliminating divergence introduced by the legacy
tools/calibrate_mu.py which used direct `requests.post` with wait_time=0.

Per schedule slot: applies a fixed `cores` to the cgroup pair (via the
standard controller_loop apply mechanism) and lets monitoring + Docker CPU
sampler measure the system. The post-hoc analysis script
(tools/parse_calibration.py) segments the resulting JSONL log per interval
to extract μ̂.

Pair with CalibrationGen (generators/calibrationgen.py) using the SAME
schedule for lam values.
"""
import os
import json
from datetime import datetime

from .controller import Controller
from .mmc_pi_controller import DockerCPUSampler


class CalibrationController(Controller):
    def __init__(self, period, schedule, *,
                 min_cores=1, max_cores=16, st=1.0, name=None,
                 container_ids=None, cpu_poll_interval=2.0,
                 enable_log=True, log_dir="./logs"):
        """
        Args:
            schedule: list of (t_start_seconds, cores_int) tuples,
                      sorted or unsorted. First entry sets init_cores.
            container_ids: list of Docker container names to sample CPU.
                           If None, u_cores logged as 0 (calibration invalid).
        """
        if not schedule:
            raise ValueError("CalibrationController requires non-empty schedule")
        # Schedule must be sorted by t_start
        schedule = sorted(schedule, key=lambda x: x[0])
        init_cores = int(schedule[0][1])
        super().__init__(period=period, init_cores=init_cores,
                          min_cores=min_cores, max_cores=max_cores,
                          st=st, name=name)
        self.schedule = schedule

        # Docker CPU sampler for measuring U_cores (Operational Utilization Law)
        self.cpu_sampler = None
        if container_ids:
            self.cpu_sampler = DockerCPUSampler(container_ids, cpu_poll_interval)
            self.cpu_sampler.start()
            print(f"[CalibrationController] CPU sampler started for {container_ids}",
                  flush=True)
        else:
            print("[CalibrationController] WARN no container_ids → u_cores=0 "
                  "(μ̂ via Utilization Law will be invalid)", flush=True)

        # JSONL log for post-hoc parsing
        self.enable_log = bool(enable_log)
        self.log_path = None
        if self.enable_log:
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.log_path = os.path.join(log_dir, f"calibration-{ts}.jsonl")
            print(f"[CalibrationController] log → {self.log_path}", flush=True)

        self._tick_count = 0

    def _target_cores_at(self, t):
        """Find the cores value for the current schedule slot."""
        target = self.schedule[0][1]
        for ts, c in self.schedule:
            if t >= ts:
                target = c
        return int(target)

    def control(self, t):
        # 1) Apply scheduled cores
        target_cores = self._target_cores_at(t)
        self.cores = float(target_cores)

        # 2) Sample observables
        rt_mean = float(self.monitoring.getRT())
        rt_p95 = float(self.monitoring.getRTp95())
        throughput = float(self.monitoring.getThroughput())  # req/s avg over window
        users = float(self.monitoring.getUsers())
        u_cores = (self.cpu_sampler.get_cores_used()
                   if self.cpu_sampler else 0.0)

        # 3) JSONL log line
        self._tick_count += 1
        if self.log_path:
            try:
                with open(self.log_path, "a") as fh:
                    fh.write(json.dumps({
                        "t": float(t),
                        "tick": self._tick_count,
                        "cores_set": target_cores,
                        "rt_mean": rt_mean,
                        "rt_p95": rt_p95,
                        "throughput": throughput,
                        "users": users,
                        "u_cores": u_cores,
                    }) + "\n")
            except Exception:
                pass
