import os
import time
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from datetime import datetime
from collections import deque
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel
from scipy.stats import norm
from .ppocontroller import PPOController, _ActorCritic, _RolloutBuf
from .controltheoretical import CTControllerScaleX

class GPPPOController(PPOController):
    """PPO autoscaler with GP-based compensation and an auxiliary PI controller."""

    # GP parameters
    _GP_INPUT_DIM = 3  # [RL action, num_users, response_time]

    def __init__(self, period, init_cores, *,
                 min_cores=1, max_cores=1000, st=0.8, name=None,
                 train=True, burst_mode="none", burst_threshold_q=20,
                 burst_threshold_r=30, burst_extra=4, trend_features=False,
                 enable_log=True, log_dir="./logs",
                 bc=5.0, dc=10.0, # PI Controller parameters (increased for responsiveness)
                 gp_train_start=100, gp_min_samples=300, gp_train_freq=50,
                 gp_max_buffer_size=300, gp_percentile=95, pi_start_time=0,
                 gp_perf_window=100, gp_error_threshold=0.2,
                 st_max=0.95, st_relaxation_factor=0.005, st_violation_threshold=0.05):
        super().__init__(period, init_cores, min_cores=min_cores,
                        max_cores=max_cores, st=st, name=name,
                        train=train, burst_mode=burst_mode,
                        burst_threshold_q=burst_threshold_q,
                        burst_threshold_r=burst_threshold_r,
                        burst_extra=burst_extra,
                        trend_features=trend_features,
                        enable_log=enable_log, log_dir=log_dir)

        # GP parameters
        self.gp_train_start = gp_train_start
        self.gp_min_samples = gp_min_samples
        self.gp_train_freq = gp_train_freq
        self.gp_percentile = gp_percentile
        self.pi_start_time = pi_start_time

        # GP performance monitoring
        self.gp_perf_window = gp_perf_window
        self.gp_error_threshold = gp_error_threshold
        self.gp_performance_errors = deque(maxlen=self.gp_perf_window)
        self.is_gp_trusted = True

        # ST auto-tuning parameters
        self.st_max = st_max
        self.st_relaxation_factor = st_relaxation_factor
        self.st_violation_threshold = st_violation_threshold

        # For ST auto-tuning using a receding horizon (circular buffer)
        self._sla_violation_history = deque(maxlen=100)

        # Initialize Auxiliary PI Controller
        self.aux_pi_controller = CTControllerScaleX(
            period=period, init_cores=init_cores, min_cores=min_cores,
            max_cores=max_cores, st=st, BC=bc, DC=dc
        )
        
        # Initialize GP
        kernel = Matern(length_scale=np.ones(self._GP_INPUT_DIM), nu=2.5) + \
                WhiteKernel(noise_level=0.1)
        self.gpr = GaussianProcessRegressor(kernel=kernel, normalize_y=True)
        self.gp_data_buffer = deque(maxlen=gp_max_buffer_size)
        self.gp_train_counter = 0
        
        # Track previous step for proper PID compensation
        self.prev_error = 0.0
        self.prev_action_ppo = 0.0
        self.prev_users = 0
        self.prev_rt = 0.0

        # Additional logging
        if self.enable_log:
            os.makedirs(log_dir, exist_ok=True)
            self.gp_log_path = os.path.join(log_dir, f"gpppo-gp-{time.time()}.log")

    def setSLA(self, sla):
        """Override to set SLA on both main and auxiliary controllers."""
        super().setSLA(sla)
        if hasattr(self, 'aux_pi_controller'):
            self.aux_pi_controller.setSLA(sla)

    def _train_gp(self):
        """Train the GP model if enough data is available."""
        print(f"Training GP with {len(self.gp_data_buffer)} samples")
        if len(self.gp_data_buffer) < self.gp_min_samples:
            return

        X = np.array([x for x, _ in self.gp_data_buffer])
        y = np.array([y for _, y in self.gp_data_buffer])
        self.gpr.fit(X, y)
        self.gp_train_counter = 0

        if self.enable_log:
            with open(self.gp_log_path, "a") as f:
                f.write(f"GP trained with {len(X)} samples\n")

    def _get_gp_prediction(self, X_pred, current_rt):
        """Get GP prediction using the specified percentile, considering error direction."""
        # Get mean and standard deviation of the prediction
        mean, std = self.gpr.predict(X_pred, return_std=True)
        
        # Gestire setpoint come lista o valore singolo (compatibilità con framework)
        setpoint = self.setpoint[0] if isinstance(self.setpoint, list) else self.setpoint
        
        # As a guardrail, we are always interested in the conservative upper bound
        # to prevent under-provisioning. We therefore always use the higher percentile.
        percentile = self.gp_percentile
        
        # Calculate the percentile value
        percentile_value = norm.ppf(percentile / 100.0, loc=mean, scale=std)
        
        return float(percentile_value.item())

    def auto_tune_st(self, min_samples=10, min_st=0.5, adjustment_factor=0.05):
        """
        Autotuning for the 'st' parameter based on the 95th percentile of SLA violations.
        This makes the controller more conservative if the SLA is consistently violated.
        It also allows 'st' to relax and increase back towards a maximum value if
        performance is consistently good.
        It uses a receding horizon of past violations.
        """
        if len(self._sla_violation_history) < min_samples:
            return

        # Calculate the 95th percentile on the history of actual SLA violations
        violation_95th_percentile = np.percentile(list(self._sla_violation_history), 95)

        # The relative violation indicates how severe the miss was compared to the target.
        if self.sla > 0:
            relative_violation = violation_95th_percentile / self.sla
        else:
            relative_violation = 0

        old_st = self.st
        new_st = self.st
        reason = ""

        # If violations are significant, become more conservative (reduce st)
        if relative_violation > self.st_violation_threshold:
            st_reduction = adjustment_factor * relative_violation
            new_st = self.st - st_reduction
            reason = f"High violation ({relative_violation:.1%})"
        # Otherwise, if performance is good, relax st (increase it)
        else:
            st_increase = self.st_relaxation_factor
            new_st = self.st + st_increase
            reason = "Good perf"
        
        # Clamp the new st value to a safe range [min_st, self.st_max].
        self.st = max(min_st, min(self.st_max, new_st))

        # If st changed, we must update the setpoint for both controllers.
        if old_st != self.st:
            self.setSLA(self.sla) # This will update self.setpoint and self.aux_pi_controller.setpoint
            print(f"AUTOTUNING ST: {reason}. st: {old_st:.3f} -> {self.st:.3f}")

    def control(self, t):
        # Chiama il controllo base del PPO controller
        super().control(t)
        ppo_cores = self.cores # This is the decision from the PPO controller
        
        # Get current metrics dopo che il PPO ha aggiornato i core
        current_rt = self.monitoring.getRT()
        num_users = self.monitoring.getUsers()
        
        # Calculate error based on previous state (that caused the PPO action)
        setpoint = self.setpoint[0] if isinstance(self.setpoint, list) else self.setpoint
        if hasattr(self, 'prev_rt') and self.prev_rt is not None:
            # Use previous RT to calculate the error that caused the PPO action
            previous_error = self.prev_rt - setpoint
        else:
            # First step, use current error
            previous_error = 0
        
        # Record SLA violations for ST auto-tuning, based on the immutable SLA goal
        if current_rt > self.sla:
            self._sla_violation_history.append(current_rt - self.sla)

        # Current error for next step (used for internal PI controller logic)
        current_error = current_rt - setpoint

        print(f"Current setpoing: {setpoint:.3f}")

        # Calculate PI compensation using the auxiliary controller
        class MockMonitoring:
            """Mocks the monitoring object to feed a specific RT to the aux controller."""
            def __init__(self, rt):
                self._rt = rt
            def getRT(self):
                return self._rt

        # Synchronize state and feed the previous RT to the auxiliary controller
        self.aux_pi_controller.cores = ppo_cores # Set current core count, not self.cores!
        self.aux_pi_controller.setMonitoring(MockMonitoring(self.prev_rt))
        
        # Get the ideal number of cores recommended by the PI controller
        self.aux_pi_controller.control(t)  # This sets aux_pi_controller.cores
        ideal_pi_cores = self.aux_pi_controller.cores

        # The compensation is the difference between the PI ideal and current state
        pi_compensation = ideal_pi_cores - ppo_cores
        
        print(f"PI compensation: ideal_cores={ideal_pi_cores:.3f} current_cores={ppo_cores:.3f} delta={pi_compensation:.3f}")
        
        # Determine compensation and store training data only after PI guardrail is active
        actual_compensation = 0
        compensation_source = "None"
        if t >= self.pi_start_time:
            # Store data for GP training using PREVIOUS step values (cause-effect relationship)
            if hasattr(self, 'prev_action_ppo') and self.step_cnt >= self.gp_train_start:
                gp_input = np.array([self.prev_action_ppo, self.prev_users, self.prev_rt])
                self.gp_data_buffer.append((gp_input, pi_compensation))

            is_gp_trained = len(self.gp_data_buffer) >= self.gp_min_samples

            # Phase 2: Use GP if trained and trusted
            if is_gp_trained and self.is_gp_trusted:
                print(f"Predicting GP with {len(self.gp_data_buffer)} samples")
                X_pred = np.array([self.prev_action_ppo, self.prev_users, self.prev_rt]).reshape(1, -1)
                gp_compensation = self._get_gp_prediction(X_pred, self.prev_rt)
                actual_compensation = gp_compensation
                compensation_source = "GP"

                # Monitor GP performance
                self.gp_performance_errors.append(abs(current_error))
                if len(self.gp_performance_errors) == self.gp_performance_errors.maxlen:
                    error_95th_p = np.percentile(list(self.gp_performance_errors), 95)
                    if error_95th_p > self.gp_error_threshold:
                        self.is_gp_trusted = False
                        self.gp_data_buffer.clear()
                        self.gp_performance_errors.clear()
                        self.aux_pi_controller.reset() # Reset PI state for fresh start
                        print(f"GP perf degraded (95th-p error {error_95th_p:.3f} > {self.gp_error_threshold:.3f}). Fallback to PI.")
                        
                        # Fallback to PI compensation for this step, recalculating with current metrics
                        self.aux_pi_controller.cores = ppo_cores
                        self.aux_pi_controller.setMonitoring(MockMonitoring(current_rt)) # Use fresh RT
                        self.aux_pi_controller.control(t)
                        pi_compensation = self.aux_pi_controller.cores - ppo_cores
                        actual_compensation = pi_compensation
                        compensation_source = "PI"

            # Phase 1: Use direct PID before GP is ready or if it's untrusted
            else:
                actual_compensation = pi_compensation
                compensation_source = "PI"
                # If GP was untrusted, check if it has been retrained and can be trusted again
                if not self.is_gp_trusted and is_gp_trained:
                    self.is_gp_trusted = True
                    print("GP has been retrained. Activating again.")

        # The guardrail should only ADD cores, never remove them.
        guardrail_compensation = max(0, actual_compensation)

        # The final decision is the PPO's choice plus any positive (upward) compensation.
        final_cores = ppo_cores + guardrail_compensation
        self.cores = max(self.min_cores, min(self.max_cores, final_cores))

        print(f"Final cores: {self.cores:.2f}, PPO: {ppo_cores:.2f}, Comp: {actual_compensation:.2f} -> Guardrail: {guardrail_compensation:.2f} ({compensation_source})")

        # Update GP training counter
        self.gp_train_counter += 1
        if self.gp_train_counter >= self.gp_train_freq:
            self._train_gp()

        # Update previous step values for next iteration
        self.prev_error = current_error  # Store the error that caused the PPO action
        if hasattr(self, 'prev_act') and self.prev_act is not None:
            self.prev_action_ppo = self.prev_act  # Store the PPO action that was just applied
        else:
            self.prev_action_ppo = 0  # Fallback if prev_act is not available
        self.prev_users = num_users
        self.prev_rt = current_rt

        # Autotuning every 30 steps
        if self.step_cnt > 0 and self.step_cnt % 30 == 0:
            self.auto_tune_st()

        # Log
        if self.enable_log:
            rt = self.monitoring.getRT()
            gp_status = f"GP:{len(self.gp_data_buffer)}/{self.gp_min_samples}"
            if len(self.gp_data_buffer) >= self.gp_min_samples:
                gp_status = "GP:ACTIVE" if self.is_gp_trusted else "GP:RE-TRAINING"
                
            line = (f"{t:.1f}s lat={rt:.2f} cores={self.cores:.2f} "
                   f"comp={guardrail_compensation:.2f} ({compensation_source}) "
                   f"rew={self.prev_reward:.2f} {gp_status} st={self.st:.3f} BC={self.aux_pi_controller.BC:.3f} DC={self.aux_pi_controller.DC:.3f}")
            print(line)
            with open(self.log_path, "a") as f:
                f.write(line + "\n")

    def reset(self):
        """Reset controller state."""
        super().reset()
        self.gp_data_buffer.clear()
        self.gp_train_counter = 0
        self._sla_violation_history.clear()
        self.gp_performance_errors.clear()
        self.is_gp_trusted = True
        if hasattr(self, 'aux_pi_controller'):
            self.aux_pi_controller.reset()
        
        # Reset previous step tracking
        self.prev_error = 0.0
        self.prev_action_ppo = 0.0
        self.prev_users = 0
        self.prev_rt = 0.0

    def set_pid_params(self, kp, ki):
        """Update PID parameters."""
        self.kp = kp
        self.ki = ki 