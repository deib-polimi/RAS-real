"""
MMCPIController — physics-informed autoscaler (no PPO, no GP, no FSM).

Architecture (each layer SWAP-able for other domains):
  • ProcessID    : online μ̂ via Operational Utilization Law
                      μ̂_per_core = X_total  /  U_total_cores
                   where X = throughput (req/s), U = CPU cores actually used.
  • PhysicalModel: M/M/c safety floor via Erlang-C numerical search.
                   c_phys = min { c : W_M/M/c(c, λ, μ̂) ≤ rt_target }
  • PIFeedback   : add-only correction on (RT_obs − SLA) with anti-windup.

Inputs (from monitoring + Docker stats):
  X      ← monitoring.getThroughput()
  RT_obs ← monitoring.getRT()
  U      ← DockerCPUSampler.get_cores_used()   (sum across all containers)

Output:
  self.cores ← c_phys + max(0, PI_correction)   (clipped to [min, max])

Generality: for AV / HVAC / robotics, replace the ProcessID estimator and
the PhysicalModel computation. The PIFeedback and the wiring stay the same.
"""
import os
import json
import math
import time
import threading
import subprocess
from collections import deque
from datetime import datetime

from .controller import Controller


# =====================================================================
#  Background CPU sampler — polls `docker stats` and exposes U_total_cores
# =====================================================================
class DockerCPUSampler(threading.Thread):
    """Polls `docker stats` every poll_interval seconds. Exposes the
    instantaneous SUM of CPU cores in use across the given container IDs
    (in units of full cores, like Prometheus container_cpu_usage rate).
    """
    def __init__(self, container_ids, poll_interval=2.0):
        super().__init__(daemon=True)
        self.container_ids = list(container_ids)
        self.poll_interval = float(poll_interval)
        self._u_cores = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last_ok_t = None
        self._fail_count = 0

    def run(self):
        while not self._stop.is_set():
            try:
                cmd = ["docker", "stats", "--no-stream", "--format",
                       "{{.CPUPerc}}", *self.container_ids]
                out = subprocess.check_output(cmd, timeout=4).decode()
                total = 0.0
                for line in out.strip().split("\n"):
                    s = line.strip().rstrip("%")
                    if s:
                        total += float(s) / 100.0
                with self._lock:
                    self._u_cores = total
                    self._last_ok_t = time.time()
                    self._fail_count = 0
            except Exception as e:
                self._fail_count += 1
                if self._fail_count <= 3 or self._fail_count % 10 == 0:
                    print(f"[DockerCPUSampler] poll fail #{self._fail_count}: {e}",
                          flush=True)
            self._stop.wait(self.poll_interval)

    def get_cores_used(self):
        with self._lock:
            return self._u_cores

    def stop(self):
        self._stop.set()


# =====================================================================
#  M/M/c with Erlang-C
# =====================================================================
def erlang_c(c: int, A: float) -> float:
    """Probability that an arrival has to wait in M/M/c.
    A = λ/μ (offered load, in Erlangs). Stable if A < c.
    Numerically stable for c ≤ ~50 via incremental A^k/k! products."""
    if c <= 0:
        return 1.0
    if A >= c:
        return 1.0
    rho = A / c
    term = 1.0      # A^0 / 0!
    sum_k = 1.0     # accumulates  Σ_{k=0..c-1} A^k/k!
    for k in range(1, c):
        term *= A / k
        sum_k += term
    term_c = term * (A / c)   # A^c / c!
    num = term_c / max(1.0 - rho, 1e-12)
    return num / (sum_k + num)


def mmc_mean_rt(c: int, lam: float, mu: float) -> float:
    """Mean response time in an M/M/c pool. Returns +inf if unstable."""
    if c <= 0 or mu <= 0:
        return float("inf")
    A = lam / mu
    if A >= c:
        return float("inf")
    rho = A / c
    Cc = erlang_c(c, A)
    return 1.0 / mu + Cc / (c * mu * (1.0 - rho))


def compute_safe_cores(lam: float, mu_hat: float, rt_target: float,
                         min_c: int, max_c: int) -> int:
    """Smallest c ∈ [min_c, max_c] such that mmc_mean_rt(c, λ, μ̂) ≤ rt_target.
    Returns max_c if no c satisfies (system physically saturated)."""
    if mu_hat is None or mu_hat <= 0 or rt_target <= 0:
        return max_c
    for c in range(max(1, int(min_c)), int(max_c) + 1):
        if mmc_mean_rt(c, lam, mu_hat) <= rt_target:
            return c
    return max_c


# =====================================================================
#  Windowed Operational Utilization Law estimator
# =====================================================================
class MuEstimator:
    """Per-core service-rate estimate via the Operational Utilization Law,
    averaged over a sliding window:  μ̂ = Σ X / Σ U  over the last `window_s`.

    The Utilization Law is an *operational* identity that holds over a
    measurement interval with many completions — it is meaningless tick-by-tick.
    Averaging X (throughput) and U (busy cores) over a window rejects the heavy
    instantaneous noise of `docker stats` under emulation. Regression fix for
    the c_phys 1↔8 oscillation observed in smoke A (23 giu 2026): the swings
    came from μ̂ jumping 1.1↔24.3, not from the PI.
    """
    def __init__(self, window_s=120.0, min_samples=10, min_busy_core_s=1.0):
        self.window_s = float(window_s)
        self.min_samples = int(min_samples)
        self.min_busy = float(min_busy_core_s)
        self._buf = deque()   # (t, X, U)

    def update(self, t, X, U):
        if X is None or U is None or U <= 0:
            return
        self._buf.append((float(t), float(X), float(U)))
        cutoff = float(t) - self.window_s
        while self._buf and self._buf[0][0] < cutoff:
            self._buf.popleft()

    def estimate(self):
        """Return μ̂ = ΣX/ΣU over the window, or None if data is insufficient
        (window not warm enough to be statistically meaningful)."""
        if len(self._buf) < self.min_samples:
            return None
        sumX = sum(x for _, x, _ in self._buf)
        sumU = sum(u for _, _, u in self._buf)
        if sumU < self.min_busy:
            return None
        return sumX / sumU


# =====================================================================
#  Controller
# =====================================================================
class MMCPIController(Controller):
    """Pure physics-informed autoscaler. See module docstring."""

    def __init__(self, period, init_cores, *,
                 min_cores=1, max_cores=8, st=1.0, name=None,
                 # M/M/c floor
                 target_frac=0.80,
                 # μ̂ estimation (windowed Utilization Law)
                 mu_window_s=120.0,
                 mu_ewma_alpha=0.10,  # deprecated: kept for config compat (unused)
                 # PI feedback (add-only)
                 kp=8.0, ki=2.0, anti_windup_max=5.0,
                 # Docker CPU sampler
                 container_ids=None,
                 cpu_poll_interval=2.0,
                 # logging
                 enable_log=True, log_dir="./logs"):
        super().__init__(period=period, init_cores=init_cores,
                          min_cores=min_cores, max_cores=max_cores,
                          st=st, name=name)

        # hyperparams
        self.target_frac = float(target_frac)
        self.mu_alpha = float(mu_ewma_alpha)
        self.kp = float(kp)
        self.ki = float(ki)
        self.aw_max = float(anti_windup_max)

        # state
        self.mu_hat = None
        self.mu_est = MuEstimator(window_s=mu_window_s)
        self.pi_I = 0.0
        self._tick_count = 0

        # CPU sampler
        self.cpu_sampler = None
        if container_ids:
            self.cpu_sampler = DockerCPUSampler(container_ids, cpu_poll_interval)
            self.cpu_sampler.start()
            print(f"[MMCPIController] CPU sampler started for {container_ids}",
                  flush=True)

        # logging
        self.enable_log = bool(enable_log)
        self.log_path = None
        if self.enable_log:
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.log_path = os.path.join(log_dir, f"mmcpi-{ts}.jsonl")

    # -----------------------------------------------------------------
    def control(self, t):
        # 1) Observations
        rt_mean = float(self.monitoring.getRT())
        lam = float(self.monitoring.getThroughput())
        u_cores = (self.cpu_sampler.get_cores_used()
                     if self.cpu_sampler else 0.0)

        # 2) Online μ̂ via WINDOWED Utilization Law (μ̂ = ΣX/ΣU over window).
        #    Rejects instantaneous docker-stats noise; only updates mu_hat once
        #    the window is statistically warm.
        mu_raw = None
        if u_cores > 0.05 and lam > 0:
            mu_raw = lam / u_cores
            self.mu_est.update(t, lam, u_cores)
        new_mu = self.mu_est.estimate()
        if new_mu is not None:
            self.mu_hat = new_mu

        # 3) M/M/c safety floor (Erlang-C numerical search)
        rt_target = self.sla * self.target_frac
        c_phys = (compute_safe_cores(lam, self.mu_hat, rt_target,
                                        self.min_cores, self.max_cores)
                   if self.mu_hat is not None else int(self.cores))

        # 4) PI feedback on RT error, add-only with SYMMETRIC anti-windup.
        #    Conditional-integration: freeze the integral whenever the output
        #    is saturated AND the error would push it further into saturation.
        #    Two saturation modes:
        #      - upper: prelim ≥ max_cores  AND err > 0   (can't add more cores)
        #      - lower: raw_corr ≤ 0        AND err < 0   (output already clamped to 0)
        #    Without the lower-saturation check, pi_I integrates negative errors
        #    indefinitely while RT < SLA and saturates at -aw_max — leaving a
        #    deficit that delays the response when drift later flips err > 0.
        err = rt_mean - self.sla
        raw_corr = self.kp * err + self.ki * self.pi_I
        prelim = c_phys + raw_corr
        saturated_up = (prelim >= self.max_cores and err > 0)
        saturated_down = (raw_corr <= 0.0 and err < 0)
        if not (saturated_up or saturated_down):
            self.pi_I += err
        self.pi_I = max(-self.aw_max, min(self.aw_max, self.pi_I))
        corr = max(0.0, self.kp * err + self.ki * self.pi_I)

        # 5) Final cores (float; controller_loop splits into int + fractional)
        final = float(c_phys) + corr
        self.cores = max(self.min_cores, min(self.max_cores, final))

        # 6) JSONL log
        self._tick_count += 1
        if self.log_path:
            try:
                with open(self.log_path, "a") as fh:
                    fh.write(json.dumps({
                        "t": float(t), "tick": self._tick_count,
                        "rt_mean": rt_mean, "lam": lam, "u_cores": u_cores,
                        "mu_raw": mu_raw, "mu_hat": self.mu_hat,
                        "c_phys": c_phys, "pi_I": self.pi_I, "pi_corr": corr,
                        "final": float(self.cores),
                    }) + "\n")
            except Exception:
                pass
