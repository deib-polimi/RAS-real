"""HandoverPPOController — PPO main + MMCPI safety guardrail with FSM handover.

ARCHITECTURE:
  • PPO inference + state update runs every tick (so PPO stays "warm")
  • Online μ̂ via Utilization Law runs every tick (so safety stays "warm")
  • FSM decides which controller's output is applied to the system

DECISION:
  • PPO_MODE: self.cores = PPO's choice (super().control sets it)
  • SAFETY_MODE: self.cores = M/M/c floor + PI correction (override)

TRANSITIONS (with hysteresis + min dwell + warmup):
  PPO → SAFETY: rt_p95(window) > sla · tau_engage_mult
  SAFETY → PPO: rt_p95(window) < sla · tau_disengage_mult AND ticks_in_safety ≥ k_dwell_min

NOTE on closed-loop perturbation: when SAFETY overrides self.cores, PPO's next
state has cores_norm reflecting safety's choice. This *can* push PPO further
OOD, but we don't care because PPO's output is ignored during SAFETY.
"""
import os
import json
import threading
from datetime import datetime

from .ppocontroller import PPOController
from .mmc_pi_controller import (DockerCPUSampler, compute_safe_cores)


class HandoverPPOController(PPOController):
    PPO_MODE = "PPO"
    SAFETY_MODE = "SAFETY"

    def __init__(self, period, init_cores, *,
                 min_cores=1, max_cores=8, st=1.0, name=None,
                 # PPO params (forwarded)
                 train=False, deterministic_eval=True,
                 burst_mode="none", trend_features=False,
                 model_suffix=None, cost_coef=0.0,
                 # Handover trigger
                 tau_engage_mult=1.2,
                 tau_disengage_mult=0.7,
                 k_dwell_min=15,
                 warmup_ticks=30,
                 # Safety (MMCPI) sub-controller params
                 target_frac=0.80,
                 mu_ewma_alpha=0.10,
                 kp=8.0, ki=2.0, anti_windup_max=5.0,
                 # CPU sampler
                 container_ids=None,
                 cpu_poll_interval=2.0,
                 # Logging
                 enable_log=True, log_dir="./logs"):
        super().__init__(period=period, init_cores=init_cores,
                          min_cores=min_cores, max_cores=max_cores, st=st,
                          name=name, train=train,
                          deterministic_eval=deterministic_eval,
                          burst_mode=burst_mode, trend_features=trend_features,
                          model_suffix=model_suffix, cost_coef=cost_coef,
                          enable_log=enable_log, log_dir=log_dir)

        # FSM trigger thresholds (resolved in setSLA)
        self.tau_engage_mult = float(tau_engage_mult)
        self.tau_disengage_mult = float(tau_disengage_mult)
        self.k_dwell_min = int(k_dwell_min)
        self.warmup_ticks = int(warmup_ticks)

        # Safety sub-controller hyperparameters
        self.target_frac = float(target_frac)
        self.mu_alpha = float(mu_ewma_alpha)
        self.kp = float(kp)
        self.ki = float(ki)
        self.aw_max = float(anti_windup_max)

        # State
        self.mu_hat = None
        self.pi_I = 0.0
        self._tick = 0
        self._mode = self.PPO_MODE
        self._ticks_in_mode = 0

        # CPU sampler
        self.cpu_sampler = None
        if container_ids:
            self.cpu_sampler = DockerCPUSampler(container_ids, cpu_poll_interval)
            self.cpu_sampler.start()
            print(f"[HandoverPPO] CPU sampler started for {container_ids}", flush=True)

        # Separate JSONL log for handover events (parallel to PPO's own .log)
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.handover_log_path = os.path.join(log_dir, f"handover-{ts}.jsonl")

    # ------------------------------------------------------------------
    def control(self, t):
        self._tick += 1
        sla = self.sla if self.sla else 0.25

        # 1) Observations (always)
        rt_mean = float(self.monitoring.getRT())
        rt_p95  = float(self.monitoring.getRTp95())
        lam     = float(self.monitoring.getThroughput())
        u_cores = (self.cpu_sampler.get_cores_used() if self.cpu_sampler else 0.0)

        # 2) Online μ̂ via Utilization Law — ALWAYS update (so safety is warm)
        mu_raw = None
        if u_cores > 0.05 and lam > 0:
            mu_raw = lam / u_cores
            self.mu_hat = (mu_raw if self.mu_hat is None
                            else self.mu_alpha * mu_raw
                                 + (1.0 - self.mu_alpha) * self.mu_hat)

        # 3) FSM transition (warmup + hysteresis + dwell)
        tau_engage    = sla * self.tau_engage_mult
        tau_disengage = sla * self.tau_disengage_mult
        prev_mode = self._mode
        if self._tick <= self.warmup_ticks:
            self._mode = self.PPO_MODE
            self._ticks_in_mode = 0
        else:
            if self._ticks_in_mode >= self.k_dwell_min:
                if self._mode == self.PPO_MODE and rt_p95 > tau_engage:
                    self._mode = self.SAFETY_MODE
                    self._ticks_in_mode = 0
                    self.pi_I = 0.0    # fresh PI on engagement
                elif self._mode == self.SAFETY_MODE and rt_p95 < tau_disengage:
                    self._mode = self.PPO_MODE
                    self._ticks_in_mode = 0
        transition = (prev_mode != self._mode)
        self._ticks_in_mode += 1

        # 4) ALWAYS run PPO to update its internal state. This also writes
        #    self.cores = PPO's chosen value. We may override it below.
        super().control(t)
        ppo_cores = int(self.cores)

        # 5) If SAFETY: compute MMCPI override and replace self.cores
        c_phys = None
        pi_corr = 0.0
        if self._mode == self.SAFETY_MODE:
            rt_target = sla * self.target_frac
            if self.mu_hat is not None and self.mu_hat > 0:
                c_phys = compute_safe_cores(lam, self.mu_hat, rt_target,
                                              self.min_cores, self.max_cores)
            else:
                c_phys = ppo_cores

            err_rt = rt_mean - sla
            raw_corr = self.kp * err_rt + self.ki * self.pi_I
            prelim = c_phys + raw_corr
            saturated_up = (prelim >= self.max_cores and err_rt > 0)
            saturated_down = (raw_corr <= 0.0 and err_rt < 0)
            if not (saturated_up or saturated_down):
                self.pi_I += err_rt
            self.pi_I = max(-self.aw_max, min(self.aw_max, self.pi_I))
            pi_corr = max(0.0, self.kp * err_rt + self.ki * self.pi_I)

            final = float(c_phys) + pi_corr
            self.cores = max(self.min_cores, min(self.max_cores, final))
        else:
            # In PPO mode, keep PI cold (so it can react fresh next time it engages)
            self.pi_I = 0.0

        # 6) Handover-specific JSONL log
        try:
            with open(self.handover_log_path, "a") as fh:
                fh.write(json.dumps({
                    "t": float(t), "tick": self._tick,
                    "mode": self._mode, "transition": transition,
                    "rt_mean": rt_mean, "rt_p95": rt_p95,
                    "lam": lam, "u_cores": u_cores,
                    "mu_raw": mu_raw, "mu_hat": self.mu_hat,
                    "ppo_cores": ppo_cores,
                    "c_phys": c_phys, "pi_I": self.pi_I, "pi_corr": pi_corr,
                    "final": float(self.cores),
                    "tau_engage": tau_engage, "tau_disengage": tau_disengage,
                }) + "\n")
        except Exception:
            pass
