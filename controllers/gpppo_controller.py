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

class GPPPOController(PPOController):
    """PPO autoscaler with GP-based compensation and PID training data generation."""

    # GP parameters
    _GP_INPUT_DIM = 3  # [RL action, num_users, response_time]

    def __init__(self, period, init_cores, *,
                 min_cores=1, max_cores=1000, st=0.8, name=None,
                 train=True, burst_mode="none", burst_threshold_q=20,
                 burst_threshold_r=30, burst_extra=4, trend_features=False,
                 enable_log=True, log_dir="./logs",
                 kp=100, ki=0.01,
                 gp_train_start=100, gp_min_samples=300, gp_train_freq=50,
                 gp_max_buffer_size=300, gp_percentile=95):
                 #kp=0.5, ki=0.05):  # PID parameters
        super().__init__(period, init_cores, min_cores=min_cores,
                        max_cores=max_cores, st=st, name=name,
                        train=train, burst_mode=burst_mode,
                        burst_threshold_q=burst_threshold_q,
                        burst_threshold_r=burst_threshold_r,
                        burst_extra=burst_extra,
                        trend_features=trend_features,
                        enable_log=enable_log, log_dir=log_dir)

        # PID parameters
        self.kp = kp  # Proportional gain
        self.ki = ki  # Integral gain

        # GP parameters
        self.gp_train_start = gp_train_start
        self.gp_min_samples = gp_min_samples
        self.gp_train_freq = gp_train_freq
        self.gp_percentile = gp_percentile

        # Initialize GP
        kernel = Matern(length_scale=np.ones(self._GP_INPUT_DIM), nu=2.5) + \
                WhiteKernel(noise_level=0.1)
        self.gpr = GaussianProcessRegressor(kernel=kernel, normalize_y=True)
        self.gp_data_buffer = deque(maxlen=gp_max_buffer_size)
        self.gp_train_counter = 0

        # Initialize PID state
        self.integral_error = 0
        
        # Track previous step for proper PID compensation
        self.prev_error = 0.0
        self.prev_action_ppo = 0.0
        self.prev_users = 0
        self.prev_rt = 0.0

        # Additional logging
        if self.enable_log:
            os.makedirs(log_dir, exist_ok=True)  # Assicurarsi che la directory esista
            self.gp_log_path = os.path.join(log_dir, f"gpppo-gp-{time.time()}.log")

    def _calculate_pid_compensation(self):
        """Calculate PID compensation based on PREVIOUS step error to correct PPO action effects."""
        # Gestire setpoint come lista o valore singolo (compatibilità con framework)
        setpoint = self.setpoint[0] if isinstance(self.setpoint, list) else self.setpoint
        
        # Use PREVIOUS error to compensate for PPO action effects from t-1
        e = self.prev_error  # Error caused by PPO action at t-1
        
        # Update integral term with previous error
        self.integral_error += e
        
        # Calculate PID output to compensate previous PPO action
        compensation = self.kp * e + self.ki * self.integral_error

        print(f"PID compensation: prev_error={e:.3f} integral={self.integral_error:.3f} compensation={compensation:.3f}")
        
        return compensation

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

    def control(self, t):
        # Get base PPO action
        if self.burst_mode in ("guard", "hybrid") and self._burst():
            self.cores = min(self.cores + self.burst_extra, self.max_cores)
            if self.burst_mode == "guard":
                self._log(t, None, self.burst_extra, guard=True)
                return

        state = self._state()
        logits, val = self.ac(torch.tensor(state, dtype=torch.float32, device=self.device))
        dist = torch.distributions.Categorical(logits=logits)
        a_idx = int(dist.sample().item())
        logp = float(dist.log_prob(torch.tensor(a_idx)))
        val = float(val)

        # Get base RL action
        delta = int(self.actions[a_idx])
        delta = max(self.min_cores - self.cores, min(delta, self.max_cores - self.cores))
        action_base_rl = delta

        # Get current metrics
        current_rt = self.monitoring.getRT()
        num_users = self.monitoring.getUsers()
        
        # Calculate current error for next step
        setpoint = self.setpoint[0] if isinstance(self.setpoint, list) else self.setpoint
        current_error = current_rt - setpoint

        print(f"Current setpoing: {setpoint:.3f}")

        # Calculate PID compensation based on PREVIOUS step error (compensates previous PPO action)
        pid_compensation = self._calculate_pid_compensation()

        # We only want to compensate for under-provisioning, so we only consider positive compensations.
        if pid_compensation < 0:
            pid_compensation = 0

        # Store data for GP training using PREVIOUS step values (cause-effect relationship)
        # Input: [prev_ppo_action, prev_users, prev_rt] → Output: current_pid_compensation
        if hasattr(self, 'prev_action_ppo') and pid_compensation > 0:  # Only train GP on under-provisioning cases
            gp_input = np.array([self.prev_action_ppo, self.prev_users, self.prev_rt])
            print(f"GP input: {gp_input} → PID compensation: {pid_compensation:.3f}")
            self.gp_data_buffer.append((gp_input, pid_compensation))

        # Get GP compensation if trained (predict compensation for current PPO action)
        gp_compensation = 0
        if len(self.gp_data_buffer) >= self.gp_min_samples:
            print(f"Predicting GP with {len(self.gp_data_buffer)} samples") 
            # Use current values to predict compensation for current PPO action
            X_pred = np.array([action_base_rl, num_users, current_rt]).reshape(1, -1)
            gp_compensation = self._get_gp_prediction(X_pred, current_rt)
            print(f"GP compensation: {gp_compensation}")

        # Phased compensation: Use direct PID until GP is trained, then switch to GP.
        actual_compensation = 0
        compensation_source = "None"

        # Phase 2: Use GP if trained and active.
        if self.step_cnt >= self.gp_train_start and len(self.gp_data_buffer) >= self.gp_min_samples:
            actual_compensation = max(0, gp_compensation) # GP also only compensates for under-provisioning
            compensation_source = "GP"
        # Phase 1: Use direct PID before GP is ready.
        else:
            actual_compensation = pid_compensation # Already clipped at 0
            compensation_source = "PID"

        final_delta = action_base_rl + actual_compensation

        final_delta = max(self.min_cores - self.cores, min(final_delta, self.max_cores - self.cores))
        print(f"Final delta: {final_delta}, action_base_rl: {action_base_rl}, {compensation_source} compensation: {actual_compensation}")
        self.cores += final_delta

        # Update PPO training
        if self.train and self.prev_state is not None:
            self.buf.store(self.prev_state, self.prev_act, self.prev_logp,
                          self._reward(), False, self.prev_val)
            if len(self.buf) >= self._ROLLOUT:
                self._update()
                self.buf.reset()

        # Update GP training counter
        self.gp_train_counter += 1
        if self.gp_train_counter >= self.gp_train_freq:
            self._train_gp()

        # Update state tracking
        self.prev_state = state
        self.prev_act = a_idx
        self.prev_logp = logp
        self.prev_val = val
        self.step_cnt += 1

        # Update previous step values for next iteration
        self.prev_error = current_error
        self.prev_action_ppo = action_base_rl
        self.prev_users = num_users
        self.prev_rt = current_rt

        # Log
        if self.enable_log:
            rt = self.monitoring.getRT()
            gp_status = f"GP:{len(self.gp_data_buffer)}/{self.gp_min_samples}" if len(self.gp_data_buffer) < self.gp_min_samples else "GP:ACTIVE"
            line = (f"{t:.1f}s lat={rt:.2f} cores={self.cores} "
                   f"Δ={final_delta:.2f} (RL:{action_base_rl:.2f} {compensation_source}:{actual_compensation:.2f}) "
                   f"rew={self.prev_reward:.2f} {gp_status}")
            print(line)
            with open(self.log_path, "a") as f:
                f.write(line + "\n")

    def reset(self):
        """Reset controller state."""
        super().reset()
        self.integral_error = 0
        self.gp_data_buffer.clear()
        self.gp_train_counter = 0
        
        # Reset previous step tracking
        self.prev_error = 0.0
        self.prev_action_ppo = 0.0
        self.prev_users = 0
        self.prev_rt = 0.0

    def set_pid_params(self, kp, ki):
        """Update PID parameters."""
        self.kp = kp
        self.ki = ki 