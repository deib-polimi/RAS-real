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
from sklearn.preprocessing import StandardScaler
from scipy.stats import norm
import multiprocessing as mp
import pickle
import copy
from .ppocontroller import PPOController, _ActorCritic, _RolloutBuf
from .controltheoretical import CTControllerScaleX

def _train_gp_worker_process(training_data, result_queue, normalize_inputs=False):
    """Worker function for GP training in separate process.

    If `normalize_inputs=True` (mock GP-R1 fix), fit a StandardScaler on X and
    pickle (scaler, gpr) so the main process can transform predictions. Otherwise
    pickle (None, gpr) for backward-compat unpacking.
    """
    try:
        X = np.array([x for x, _ in training_data])
        y = np.array([y for _, y in training_data])

        scaler = None
        if normalize_inputs:
            scaler = StandardScaler().fit(X)
            X_fit = scaler.transform(X)
        else:
            X_fit = X

        # Create a new GP instance for training
        kernel = Matern(length_scale=np.ones(5), nu=2.5) + \
                WhiteKernel(noise_level=0.1)
        new_gpr = GaussianProcessRegressor(kernel=kernel, normalize_y=True)

        # Train the model
        new_gpr.fit(X_fit, y)

        # Serialize the trained model with error handling
        try:
            model_bytes = pickle.dumps((scaler, new_gpr), protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            result_queue.put(('error', f'Serialization failed: {e}', 0))
            return

        # Send result back to main process
        result_queue.put(('success', model_bytes, len(X)))

    except Exception as e:
        result_queue.put(('error', str(e), 0))

class GPPPOController(PPOController):
    """PPO autoscaler with GP-based compensation and an auxiliary PI controller."""

    # GP parameters
    _GP_INPUT_DIM = 5  # [RL action, num_users, response_time, sin_t, cos_t]

    def __init__(self, period, init_cores, *,
                 min_cores=1, max_cores=1000, st=0.8, name=None,
                 train=True, burst_mode="none", burst_threshold_q=20,
                 burst_threshold_r=30, burst_extra=4, trend_features=False,
                 enable_log=True, log_dir="./logs",
                 bc=5.0, dc=10.0, # PI Controller parameters (increased for responsiveness)
                 gp_train_start=100, gp_min_samples=300, gp_train_freq=50,
                 gp_max_buffer_size=300, gp_percentile=95, pi_start_time=0,
                 gp_perf_window=100, gp_violation_threshold=0.05, # Threshold for 95th percentile of SLA violations
                 st_max=0.95, st_relaxation_factor=0.005, st_violation_threshold=0.05,
                 min_st=0.5, gp_time_period=200, # Period for temporal features
                 gp_target_mode="pi_compensation", # GP target choice: "pi_compensation" (default, A3 bug) or "sla_shortfall" (mock GP-R2 fix)
                 gp_async=True, # If False, train GP synchronously in main process (use for fast simulators where mp.Process spawn is too slow)
                 gp_normalize_inputs=False, # If True, fit StandardScaler on GP inputs (mock GP-R1 fix)
                 gp_trust_mode="outcome", # "outcome" (default, current) or "calibration" (mock SAFE-R3): distrust when posterior σ is mis-calibrated wrt observed targets
                 gp_calibration_window=30, # window of recent residual-z² for calibration check
                 gp_miscalibration_thresh=0.20, # if > this fraction of |z|>2, distrust
                 gp_distrust_dwell=0, # mock SAFE-R1: # of ticks distrust persists. 0 = current B2 single-tick fallback bug
                 gp_lookahead_horizon=0, # knob H: predict over a window. 0 = current 1-tick ahead.
                 gp_adaptive_train=False,         # knob #3: trigger retraining on drift detection
                 gp_drift_threshold=1.5,          # z-score threshold for detecting drift in target buffer
                 gp_min_train_interval=10,        # min ticks between adaptive retrainings (anti-thrashing)
                 gp_eviction_keep=0,              # when drift fires, evict buffer to last K (0=disabled)
                 # ---- aux PI configuration (forwarded to internal CTControllerScaleX) ----
                 pi_anti_windup=False, pi_e_clip=None,
                 pi_error_form="inverse", pi_rt_deadband_frac=0.0):
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
        self.gp_time_period = gp_time_period

        # GP performance monitoring
        self.gp_perf_window = gp_perf_window
        self.gp_violation_threshold = gp_violation_threshold
        self.gp_performance_errors = deque(maxlen=self.gp_perf_window)
        self.is_gp_trusted = True

        # Mock-fix GP-R2: choice of GP target signal
        self.gp_target_mode = gp_target_mode
        # Synchronous training fallback (for simulator runs where mp.Process spawn is too slow)
        self.gp_async = gp_async
        # Mock-fix GP-R1: StandardScaler on GP inputs
        self.gp_normalize_inputs = gp_normalize_inputs
        self._x_scaler = None  # populated by _check_training_result on success
        # Mock-fix SAFE-R3: calibration-based trust gate
        self.gp_trust_mode = gp_trust_mode
        self.gp_calibration_window = gp_calibration_window
        self.gp_miscalibration_thresh = gp_miscalibration_thresh
        self._gp_residual_z2 = deque(maxlen=gp_calibration_window)
        self._last_gp_mean = None
        self._last_gp_std = None
        # Mock-fix SAFE-R1: dwell-time after distrust (prevents single-tick fallback bug B2)
        self.gp_distrust_dwell = gp_distrust_dwell
        self._distrust_remaining = 0
        # Knob H: prediction horizon. When > 0, GP target = max RT shortfall over
        # the next H ticks. Pending buffer holds (input, ppo_cores, [rts]) tuples
        # that get committed to gp_data_buffer after H+1 RT observations.
        self.gp_lookahead_horizon = int(gp_lookahead_horizon)
        self._gp_pending: deque = deque()
        # Knob #3 (adaptive retraining): detect drift in target buffer via z-score
        # comparison between recent/older windows, retrain immediately when detected.
        self.gp_adaptive_train = gp_adaptive_train
        self.gp_drift_threshold = float(gp_drift_threshold)
        self.gp_min_train_interval = int(gp_min_train_interval)
        # Optional buffer eviction on drift: discards pre-drift samples, retraining
        # the GP only on the (last K) post-drift data. Addresses the "buffer
        # composition" bottleneck where stale samples dominate over fresh ones.
        self.gp_eviction_keep = int(gp_eviction_keep)

        # ST auto-tuning parameters
        self.st_max = st_max
        self.st_relaxation_factor = st_relaxation_factor
        self.st_violation_threshold = st_violation_threshold
        self.min_st = min_st

        # For ST auto-tuning using a receding horizon (circular buffer)
        self._sla_violation_history = deque(maxlen=100)

        # Initialize Auxiliary PI Controller — forward the PI configuration so that
        # cloud config.json can fully parameterise GPPPO without post-construction tweaks.
        self.aux_pi_controller = CTControllerScaleX(
            period=period, init_cores=init_cores, min_cores=min_cores,
            max_cores=max_cores, st=st, BC=bc, DC=dc,
            anti_windup=pi_anti_windup, e_clip=pi_e_clip,
            error_form=pi_error_form, rt_deadband_frac=pi_rt_deadband_frac,
        )
        
        # Initialize GP
        kernel = Matern(length_scale=np.ones(self._GP_INPUT_DIM), nu=2.5) + \
                WhiteKernel(noise_level=0.1)
        self.gpr = GaussianProcessRegressor(kernel=kernel, normalize_y=True)
        self.gp_data_buffer = deque(maxlen=gp_max_buffer_size)
        self.gp_train_counter = 0
        
        # Async training variables
        self.gp_training_process = None
        self.gp_training_in_progress = False
        self.gp_training_start_time = None
        self.gp_training_queue = mp.Queue()
        self.gp_training_result_queue = mp.Queue()
        
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
        """Train the GP model asynchronously if enough data is available."""
        # Safety check: ensure no training is already in progress
        if self.gp_training_in_progress:
            print("GP training already in progress, skipping...")
            return
            
        # Check if previous training process is still running
        if self.gp_training_process and self.gp_training_process.is_alive():
            # Check if training is taking too long (timeout after 60 seconds)
            if self.gp_training_start_time and (time.time() - self.gp_training_start_time) > 60:
                print("GP training timeout, forcing termination...")
                self._terminate_training_process()
            else:
                print("Previous GP training process still running, skipping...")
                return
                
        if len(self.gp_data_buffer) < self.gp_min_samples:
            return

        # Copy data for process safety
        training_data = copy.deepcopy(list(self.gp_data_buffer))
        self.gp_training_in_progress = True
        self.gp_training_start_time = time.time()

        if not self.gp_async:
            # Synchronous training in main process — used by fast simulators
            print(f"Starting SYNC GP training with {len(training_data)} samples")
            try:
                _train_gp_worker_process(training_data, self.gp_training_result_queue,
                                          self.gp_normalize_inputs)
            finally:
                self.gp_train_counter = 0
            return

        print(f"Starting async GP training with {len(training_data)} samples")

        # Start training in background process
        self.gp_training_process = mp.Process(
            target=_train_gp_worker_process,
            args=(training_data, self.gp_training_result_queue, self.gp_normalize_inputs)
        )
        self.gp_training_process.daemon = True  # Ensure process is terminated when main process exits
        self.gp_training_process.start()
        
        self.gp_train_counter = 0

    def _terminate_training_process(self):
        """Safely terminate the training process and clean up."""
        if self.gp_training_process and self.gp_training_process.is_alive():
            try:
                self.gp_training_process.terminate()
                self.gp_training_process.join(timeout=10.0)  # Increased timeout
                
                # Force kill if still alive
                if self.gp_training_process.is_alive():
                    print("Force killing GP training process...")
                    self.gp_training_process.kill()
                    self.gp_training_process.join(timeout=5.0)
                    
            except Exception as e:
                print(f"Error terminating training process: {e}")
            finally:
                self.gp_training_in_progress = False
                self.gp_training_start_time = None
                self.gp_training_process = None

    def _check_training_result(self):
        """Check if training process has completed and update model."""
        if not self.gp_training_in_progress:
            return

        # Sync training: result is already in the queue, no process to poll.
        # Async training: skip if subprocess still running.
        if self.gp_async and (not self.gp_training_process or self.gp_training_process.is_alive()):
            return
            
        # Process has finished, check result
        try:
            # Use timeout to avoid blocking indefinitely
            result = self.gp_training_result_queue.get(timeout=0.1)
            status, data, num_samples = result
            
            if status == 'success':
                # Deserialize and update the model with error handling
                try:
                    payload = pickle.loads(data)
                    # Backward-compat: payload may be (scaler, gpr) tuple or just gpr
                    if isinstance(payload, tuple) and len(payload) == 2:
                        new_scaler, new_gpr = payload
                    else:
                        new_scaler, new_gpr = None, payload
                    self.gpr = new_gpr
                    self._x_scaler = new_scaler
                    training_time = time.time() - self.gp_training_start_time
                    print(f"Async GP training completed with {num_samples} samples in {training_time:.2f}s")
                    
                    if self.enable_log:
                        with open(self.gp_log_path, "a") as f:
                            f.write(f"Async GP trained with {num_samples} samples\n")
                except Exception as e:
                    print(f"GP model deserialization failed: {e}")
                    
            else:
                print(f"GP training failed: {data}")
                
        except Exception as e:
            # Queue timeout or other error - this is normal if no result yet
            if "timeout" not in str(e).lower():
                print(f"Error checking training result: {e}")
        finally:
            # Clean up
            self.gp_training_in_progress = False
            self.gp_training_start_time = None
            self.gp_training_process = None

    def _detect_drift_in_buffer(self) -> bool:
        """Detect drift via RT distribution shift (z-score window comparison).

        Uses observed RT (prev_rt at index 2 of gp_input) as the drift signal.
        Crucially, RT shifts even when the controller successfully compensates
        — unlike the target signal `cores·max(0,rt-sla)/sla` which is MASKED to
        ~0 whenever the controller keeps RT below SLA. This RT-based detector
        catches both observable (λ change) and unobservable (μ degradation) drift.
        """
        win = 20
        if len(self.gp_data_buffer) < 2 * win:
            return False
        # Extract prev_rt from each (gp_input, target) tuple — input index 2
        rts = np.array([x[2] for x, _ in list(self.gp_data_buffer)])
        recent = rts[-win:]
        older  = rts[-2 * win:-win]
        std_r, std_o = float(recent.std()), float(older.std())
        pooled = np.sqrt((std_r ** 2 + std_o ** 2) / 2.0)
        # Floor on pooled_std (RT scale) prevents false positives in quasi-stable regimes
        pooled = max(pooled, 0.02)
        z_shift = abs(float(recent.mean()) - float(older.mean())) / pooled
        return bool(z_shift > self.gp_drift_threshold)

    def _get_gp_prediction(self, X_pred, current_rt):
        """Get GP prediction using the specified percentile, considering error direction."""
        # Check if training is in progress
        if self.gp_training_in_progress:
            print("GP training in progress, skipping prediction")
            return 0.0
        
        # Perform prediction
        try:
            X_in = self._x_scaler.transform(X_pred) if self._x_scaler is not None else X_pred
            mean, std = self.gpr.predict(X_in, return_std=True)
        except Exception as e:
            print(f"GP prediction error: {e}")
            return 0.0

        # Stash mean/std for calibration-based trust check at next tick.
        try:
            self._last_gp_mean = float(np.asarray(mean).item())
            self._last_gp_std  = float(np.asarray(std).item())
        except Exception:
            self._last_gp_mean = self._last_gp_std = None

        # Gestire setpoint come lista o valore singolo (compatibilità con framework)
        setpoint = self.setpoint[0] if isinstance(self.setpoint, list) else self.setpoint

        # As a guardrail, we are always interested in the conservative upper bound
        # to prevent under-provisioning. We therefore always use the higher percentile.
        percentile = self.gp_percentile

        # Calculate the percentile value
        percentile_value = norm.ppf(percentile / 100.0, loc=mean, scale=std)

        return float(percentile_value.item())

    def auto_tune_st(self, min_samples=10, adjustment_factor=0.05):
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
        
        # Clamp the new st value to a safe range [self.min_st, self.st_max].
        self.st = max(self.min_st, min(self.st_max, new_st))

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
        
        # Calculate temporal features for GP input
        sin_t = np.sin(2 * np.pi * t / self.gp_time_period)
        cos_t = np.cos(2 * np.pi * t / self.gp_time_period)
        
        # Determine compensation and store training data only after PI guardrail is active
        actual_compensation = 0
        compensation_source = "None"
        if t >= self.pi_start_time:
            # Store data for GP training using PREVIOUS step values (cause-effect relationship)
            if hasattr(self, 'prev_action_ppo') and self.step_cnt >= self.gp_train_start:
                gp_input = np.array([self.prev_action_ppo, self.prev_users, self.prev_rt, sin_t, cos_t])

                if self.gp_lookahead_horizon > 0 and self.gp_target_mode == "sla_shortfall":
                    # Knob H: pending-buffer logic. Append now, observe rt[t..t+H], commit later.
                    self._gp_pending.append({"input": gp_input,
                                              "ppo_cores": ppo_cores,
                                              "rts": []})
                    # Each in-flight pending entry observes this tick's RT.
                    for entry in self._gp_pending:
                        entry["rts"].append(current_rt)
                    # Commit entries that have collected H+1 observations (worst-case lookahead).
                    while self._gp_pending and len(self._gp_pending[0]["rts"]) >= self.gp_lookahead_horizon + 1:
                        done = self._gp_pending.popleft()
                        worst_rt = max(done["rts"])
                        if worst_rt > self.sla and self.sla > 0:
                            t_target = done["ppo_cores"] * (worst_rt - self.sla) / self.sla
                        else:
                            t_target = 0.0
                        self.gp_data_buffer.append((done["input"], t_target))
                else:
                    # Immediate target (H=0 path) — original behaviour.
                    if self.gp_target_mode == "sla_shortfall":
                        if current_rt > self.sla and self.sla > 0:
                            gp_target = ppo_cores * (current_rt - self.sla) / self.sla
                        else:
                            gp_target = 0.0
                    else:
                        gp_target = pi_compensation
                    self.gp_data_buffer.append((gp_input, gp_target))

                # Mock SAFE-R3: track GP posterior calibration vs observed targets.
                # If too many residuals fall outside the predicted ±2σ band, the GP
                # is mis-calibrated → distrust until a fresh training cycle.
                if (self.gp_trust_mode == "calibration"
                    and self._last_gp_mean is not None
                    and self._last_gp_std is not None
                    and self.is_gp_trusted):
                    z = (gp_target - self._last_gp_mean) / max(self._last_gp_std, 1e-3)
                    self._gp_residual_z2.append(z * z)
                    if len(self._gp_residual_z2) == self._gp_residual_z2.maxlen:
                        miscal_frac = sum(1 for z2 in self._gp_residual_z2 if z2 > 4.0) \
                                      / len(self._gp_residual_z2)
                        if miscal_frac > self.gp_miscalibration_thresh:
                            self.is_gp_trusted = False
                            self._distrust_remaining = self.gp_distrust_dwell
                            self._gp_residual_z2.clear()
                            print(f"[SAFE-R3] GP miscalibrated "
                                  f"(frac |z|>2: {miscal_frac:.2f}). Distrust dwell={self._distrust_remaining}.")

            is_gp_trained = len(self.gp_data_buffer) >= self.gp_min_samples

            # Phase 2: Use GP if trained and trusted
            if is_gp_trained and self.is_gp_trusted:
                print(f"Predicting GP with {len(self.gp_data_buffer)} samples")
                X_pred = np.array([self.prev_action_ppo, self.prev_users, self.prev_rt, sin_t, cos_t]).reshape(1, -1)
                gp_compensation = self._get_gp_prediction(X_pred, self.prev_rt)
                actual_compensation = gp_compensation
                compensation_source = "GP"

                # Monitor GP performance by tracking the magnitude of SLA violations
                sla_violation = max(0, current_rt - self.sla)
                self.gp_performance_errors.append(sla_violation)

                # Outcome-based distrust trigger only fires under trust_mode="outcome".
                # In calibration mode, distrust is driven by posterior mis-calibration above.
                if (self.gp_trust_mode == "outcome"
                    and len(self.gp_performance_errors) == self.gp_performance_errors.maxlen):
                    violation_95th_p = np.percentile(list(self.gp_performance_errors), 95)
                    if violation_95th_p > self.gp_violation_threshold:
                        self.is_gp_trusted = False
                        self._distrust_remaining = self.gp_distrust_dwell
                        # Keep the training data - only reset performance monitoring
                        # self.gp_data_buffer.clear()  # REMOVED: preserve training data
                        self.gp_performance_errors.clear()
                        self.aux_pi_controller.reset() # Reset PI state for fresh start
                        log_msg = f"GP perf degraded (95th-p violation {violation_95th_p:.3f} > {self.gp_violation_threshold:.3f}). Fallback to PI."
                        print(log_msg)
                        if self.enable_log:
                            with open(self.log_path, "a") as f:
                                f.write(f"EVENT @{t:.1f}s: {log_msg}\n")
                        
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
                # If GP was untrusted, check if it has been retrained and can be trusted again.
                # Mock SAFE-R1: respect dwell-time before re-trusting (prevents B2 single-tick bug).
                if not self.is_gp_trusted and is_gp_trained:
                    if self._distrust_remaining > 0:
                        self._distrust_remaining -= 1
                        # stay distrusted; PI takes over for this tick
                    else:
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
        should_train = self.gp_train_counter >= self.gp_train_freq
        if (not should_train) and self.gp_adaptive_train and \
           self.gp_train_counter >= self.gp_min_train_interval and \
           self._detect_drift_in_buffer():
            print(f"[ADAPTIVE-TRAIN] drift detected at t={t}, retrain triggered "
                  f"(early at counter={self.gp_train_counter})")
            should_train = True
            # Evict pre-drift samples so retraining uses only fresh post-drift data.
            if self.gp_eviction_keep > 0 and len(self.gp_data_buffer) > self.gp_eviction_keep:
                keep = list(self.gp_data_buffer)[-self.gp_eviction_keep:]
                self.gp_data_buffer.clear()
                self.gp_data_buffer.extend(keep)
                print(f"[ADAPTIVE-EVICT] buffer pruned to last {len(keep)} samples")
        if should_train:
            self._train_gp()

        # Check if training has completed
        self._check_training_result()

        # Update previous step values for next iteration
        self.prev_error = current_error  # Store the error that caused the PPO action
        if hasattr(self, 'prev_act') and self.prev_act is not None:
            self.prev_action_ppo = int(self.actions[self.prev_act])  # delta cores ∈ {-2..+2}, not index
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
            gp_perf_metric_str = ""

            if len(self.gp_data_buffer) >= self.gp_min_samples:
                gp_status = "GP:ACTIVE" if self.is_gp_trusted else "GP:RE-TRAINING"
                
                # If GP is active and we have enough data to judge, calculate and show the performance metric
                if self.is_gp_trusted and len(self.gp_performance_errors) == self.gp_performance_errors.maxlen:
                    violation_95th_p = np.percentile(list(self.gp_performance_errors), 95)
                    gp_perf_metric_str = f" gp_viol_p95={violation_95th_p:.3f}"

            line = (f"{t:.1f}s lat={rt:.2f} cores={self.cores:.2f} "
                   f"comp={guardrail_compensation:.2f} ({compensation_source}) "
                   f"rew={self.prev_reward:.2f} {gp_status}{gp_perf_metric_str} st={self.st:.3f} "
                   f"BC={self.aux_pi_controller.BC:.3f} DC={self.aux_pi_controller.DC:.3f}")
            print(line)
            with open(self.log_path, "a") as f:
                f.write(line + "\n")

    def reset(self):
        """Reset controller state."""
        super().reset()
        
        # Stop any ongoing GP training
        if self.gp_training_process and self.gp_training_process.is_alive():
            print("Terminating GP training process...")
            self._terminate_training_process()
        
        # Clear both queues
        self._clear_training_queues()
        
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

    def _clear_training_queues(self):
        """Clear all training queues safely."""
        # Clear result queue
        while True:
            try:
                self.gp_training_result_queue.get_nowait()
            except:
                break
                
        # Clear training queue (if used in future)
        while True:
            try:
                self.gp_training_queue.get_nowait()
            except:
                break

    def set_pid_params(self, kp, ki):
        """Update PID parameters."""
        self.kp = kp
        self.ki = ki

    def __del__(self):
        """Destructor to ensure proper cleanup."""
        try:
            if hasattr(self, 'gp_training_process') and self.gp_training_process:
                self._terminate_training_process()
        except:
            pass  # Ignore errors during cleanup 