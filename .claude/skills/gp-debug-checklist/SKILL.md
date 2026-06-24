---
name: gp-debug-checklist
description: Checklist for debugging the GP in GPPPOController. TRIGGER when discussing GP convergence, kernel choice, length scale, posterior variance, predictions returning 0, pickle/serialization errors, async-training races, or GP trust falling.
---

# GP Debug Checklist (GPPPOController)

When something looks off with the GP, walk through these in order. Stop at the first one that matches.

## 1. Buffer state
```python
len(controller.gp_data_buffer)  # < gp_min_samples (300) → GP cannot predict, returns 0.0
```
- If buffer is full (=300) and never grows: that's expected (FIFO maxlen). Confirm new samples are arriving.
- If buffer never reaches 300: check `t >= pi_start_time` and `step_cnt >= gp_train_start`.

## 2. Async training in progress
```python
controller.gp_training_in_progress  # if True, predict() short-circuits to 0.0
```
- Check `gp_training_process.is_alive()` and elapsed time vs 60s timeout.
- If stuck >60s: `_terminate_training_process` should have fired — verify it did.

## 3. Input semantics (BUG A1)
The GP input vector is `[prev_action_ppo, prev_users, prev_rt, sin_t, cos_t]`.
- `prev_action_ppo` is currently the **action index** (0..4), not the **delta cores** (-2..+2). Verify with:
  ```python
  controller.prev_action_ppo  # should be in {-2,-1,0,1,2}, currently in {0..4}
  ```
- Fix: in `gpppo_controller.py:425`, replace `self.prev_act` with `int(self.actions[self.prev_act])`.

## 4. Kernel + length-scale
- Default: `Matern(length_scale=ones(5), nu=2.5) + WhiteKernel(noise_level=0.1)`.
- Without `normalize_y` and without input scaling, length-scales will be off-scale across dims (users 0-1000 vs sin_t in [-1,1]).
- Diagnostic:
  ```python
  print(controller.gpr.kernel_)  # after fit, see learned length-scales
  ```
  If any length-scale is at the bound → marginal-likelihood didn't identify it.

## 5. Posterior variance collapse
```python
mean, std = controller.gpr.predict(X_pred, return_std=True)
print(std)  # if ~0 everywhere, posterior collapsed; predictions are overconfident
```
- Common cause: `WhiteKernel(noise_level=0.1)` fixed and target nearly noiseless → kernel says "I know this exactly".
- Fix: `WhiteKernel(noise_level=0.1, noise_level_bounds=(1e-5, 1e1))` to let MLE tune it.

## 6. Trust mechanism stuck
```python
controller.is_gp_trusted  # if False but data buffer ≥ min_samples, it'll re-trust on next tick (BUG A4)
```
- Fallback to PI lasts only one tick. To extend, add hysteresis: require N successful ticks before re-trusting.

## 7. Pickle / serialization
- If `_train_gp_worker_process` returns `('error', 'Serialization failed: ...')`:
  - Likely a sklearn version mismatch between main and child process.
  - Or: a custom kernel that's not picklable. We use stock kernels — should not happen.
- Verify Python and sklearn versions match (`mp.set_start_method("spawn")` is the safe default).

## 8. Race between predict() and fit()
- `predict()` uses `self.gpr`. `_check_training_result` swaps `self.gpr` to a new pickled object.
- Race window: predict reads old gpr → swap happens → next predict uses new. Not a correctness bug, but if you see "weird" jumps in predictions, this is why.

## 9. GP target semantics (research-level concern, not a bug)
- Target is `pi_compensation`. So the GP is essentially a Bayesian wrapper of the PI.
- If you're trying to claim "GP learns PPO's error" in the paper, this is misleading. Either:
  - Reframe the claim ("GP gives uncertainty-aware PI"), or
  - Change the target to e.g. `cores_oracle(rt) - ppo_cores`.

## 10. When all else looks fine but performance is bad
- Check `gp_violation_threshold=0.05` — too tight will make GP perpetually untrusted.
- Check `gp_perf_window=100` — too large delays detection of degradation.

## Quick sanity test
```python
from controllers.gpppo_controller import GPPPOController
c = GPPPOController(period=1, init_cores=2)
# Manually inject 300 fake samples to bypass training trigger
import numpy as np
for _ in range(300):
    c.gp_data_buffer.append((np.random.randn(5), np.random.randn()))
c._train_gp()
# Wait for async training, then check:
# - kernel learned
# - prediction returns finite mean+std
```
