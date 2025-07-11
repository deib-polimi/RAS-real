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
                 gp_max_buffer_size=300, gp_percentile=95):
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
        
        # Determine which percentile to use based on error direction
        error = current_rt - setpoint  # RT too high -> positive error -> add resources
        if error > 0:  # RT is too high, we want to scale up
            percentile = self.gp_percentile  # Use lower percentile to be conservative when adding resources
        else:  # RT is too low, we want to scale down
            percentile = 100 - self.gp_percentile  # Use higher percentile to be conservative when removing resources
        
        # Calculate the percentile value
        percentile_value = norm.ppf(percentile / 100.0, loc=mean, scale=std)
        
        #return float(percentile_value.item())
        return float(mean)

    def auto_tune_pi(self, window=20, high_err=0.05, low_err=0.01, up_factor=1.2, down_factor=0.8, max_gain=25.0, min_gain=1.0):
        """Autotuning semplice: aumenta BC/DC se errore medio alto, li riduce se basso."""
        if not hasattr(self, '_error_history'):
            self._error_history = []
        # Salva errore corrente
        self._error_history.append(abs(self.prev_error))
        if len(self._error_history) > window:
            self._error_history.pop(0)
        # Solo se abbiamo abbastanza dati
        if len(self._error_history) < window:
            return
        mean_err = np.mean(self._error_history)
        old_bc = self.aux_pi_controller.BC
        old_dc = self.aux_pi_controller.DC
        if mean_err > high_err:
            self.aux_pi_controller.BC = min(self.aux_pi_controller.BC * up_factor, max_gain)
            self.aux_pi_controller.DC = min(self.aux_pi_controller.DC * up_factor, max_gain)
            print(f"AUTOTUNING: Errore alto ({mean_err:.3f}), aumentando BC: {old_bc:.3f}->{self.aux_pi_controller.BC:.3f}, DC: {old_dc:.3f}->{self.aux_pi_controller.DC:.3f}")
        elif mean_err < low_err:
            self.aux_pi_controller.BC = max(self.aux_pi_controller.BC * down_factor, min_gain)
            self.aux_pi_controller.DC = max(self.aux_pi_controller.DC * down_factor, min_gain)
            print(f"AUTOTUNING: Errore basso ({mean_err:.3f}), riducendo BC: {old_bc:.3f}->{self.aux_pi_controller.BC:.3f}, DC: {old_dc:.3f}->{self.aux_pi_controller.DC:.3f}")

    def control(self, t):
        # Chiama il controllo base del PPO controller
        super().control(t)
        
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
        
        # Current error for next step
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
        self.aux_pi_controller.cores = self.cores # Set current core count
        self.aux_pi_controller.setMonitoring(MockMonitoring(self.prev_rt))
        
        # Get the ideal number of cores recommended by the PI controller
        self.aux_pi_controller.control(t)  # This sets aux_pi_controller.cores
        ideal_pi_cores = self.aux_pi_controller.cores

        # The compensation is the difference between the PI ideal and current state
        pi_compensation = ideal_pi_cores - self.cores
        
        print(f"PI compensation: ideal_cores={ideal_pi_cores:.3f} current_cores={self.cores:.3f} delta={pi_compensation:.3f}")

        # Store data for GP training using PREVIOUS step values (cause-effect relationship)
        # Input: [prev_ppo_action, prev_users, prev_rt] → Output: current_pid_compensation
        if hasattr(self, 'prev_action_ppo') and self.step_cnt >= self.gp_train_start:  # Train GP on both under-provisioning and over-provisioning cases
            gp_input = np.array([self.prev_action_ppo, self.prev_users, self.prev_rt])
            print(f"GP input: {gp_input} → PI compensation: {pi_compensation:.3f}")
            self.gp_data_buffer.append((gp_input, pi_compensation))

        # Get GP compensation if trained (predict compensation for current PPO action)
        gp_compensation = 0
        if len(self.gp_data_buffer) >= self.gp_min_samples and self.step_cnt >= self.gp_train_start:
            print(f"Predicting GP with {len(self.gp_data_buffer)} samples") 
            # Use previous values to predict compensation for the error that caused the PPO action
            X_pred = np.array([self.prev_action_ppo, self.prev_users, self.prev_rt]).reshape(1, -1)
            gp_compensation = self._get_gp_prediction(X_pred, self.prev_rt)
            print(f"GP compensation: {gp_compensation}")

        # Phased compensation: Use direct PID until GP is trained, then switch to GP.
        actual_compensation = 0
        compensation_source = "None"
        ppo_cores = self.cores # This is the decision from the PPO controller

        # Phase 2: Use GP if trained and active.
        if self.step_cnt >= self.gp_train_start and len(self.gp_data_buffer) >= self.gp_min_samples:
            actual_compensation =  gp_compensation
            compensation_source = "GP"
        # Phase 1: Use direct PID before GP is ready.
        else:
            actual_compensation = pi_compensation
            compensation_source = "PI"

        # The guardrail should only ADD cores, never remove them.
        # We only apply positive compensation to what PPO decided.
        # If compensation is negative, we ignore it.
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

        # Autotuning ogni 20 step
        if self.step_cnt % 20 == 0:
            self.auto_tune_pi()

        # Log
        if self.enable_log:
            rt = self.monitoring.getRT()
            gp_status = f"GP:{len(self.gp_data_buffer)}/{self.gp_min_samples}" if len(self.gp_data_buffer) < self.gp_min_samples else "GP:ACTIVE"
            line = (f"{t:.1f}s lat={rt:.2f} cores={self.cores} "
                   f"compensation={actual_compensation:.2f} ({compensation_source}) "
                   f"rew={self.prev_reward:.2f} {gp_status} BC={self.aux_pi_controller.BC:.3f} DC={self.aux_pi_controller.DC:.3f}")
            print(line)
            with open(self.log_path, "a") as f:
                f.write(line + "\n")

    def reset(self):
        """Reset controller state."""
        super().reset()
        self.gp_data_buffer.clear()
        self.gp_train_counter = 0
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