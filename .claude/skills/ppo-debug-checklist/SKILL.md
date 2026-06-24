---
name: ppo-debug-checklist
description: Checklist for debugging PPOController. TRIGGER when PPO oscillates, never converges, action distribution collapses, value loss explodes, reward looks wrong, or the agent does nothing useful.
---

# PPO Debug Checklist (PPOController)

## 1. Reward signal sanity
```python
# Reward = -|asym_pen_lat|, asymmetric: 0.6 for over-SLA, 0.4 for under
# Always negative or zero → max possible is 0
```
- If reward is constantly very negative → SLA is being violated constantly → controller can't catch up.
- If reward is constantly ~0 → over-provisioning; agent has no signal to learn from.
- **Diagnostic**: log `(rt, setpoint, reward)` per tick for 100 ticks; reward should vary.

## 2. State normalization
State: `[lat_ratio, q/100, r/1000, trend_p95, cores_norm]`
- `lat_ratio = min(2.0, p95/setpoint)` → clipped at 2.0, can hide extreme regimes.
- `q/100` → assumes queue length ~O(100). For high-load runs, q can be 10000+ → state explodes.
- `r/1000` → assumes arrival rate ~O(1000) req/s.
- If your workload is far from these scales, the network sees inputs out of distribution.

## 3. Value function divergence
- No clipped value loss in `_update()` — vanilla MSE.
- If `v_loss` grows monotonically → value head is diverging.
- **Fix**: add value clipping (`vp_clipped = vp_old + clip(vp - vp_old, -clip, clip)`) or reduce `_LR`.

## 4. Entropy collapse
- `_ENT_COEF=0.01` is on the low end.
- If action distribution becomes deterministic too early → exploitation locked in.
- **Diagnostic**: log `dist.entropy().mean()` per update; should stay > 0.5 of max early on.

## 5. Rollout vs episode length
- `_ROLLOUT=512` → with `period=3s` that's 25 minutes per update; with `period=1s`, 8.5 minutes.
- If experiments are short, you might do 0-1 updates total → policy never moves.

## 6. Action space saturation
- Actions `[-2,-1,0,+1,+2]`. If the agent always picks ±2, it's saturating → action space too small.
- **Diagnostic**: histogram of `a_idx` over a run.

## 7. Burst guard interactions
- `burst_mode in ("guard","hybrid")` short-circuits `control()` → no rollout sample stored.
- If burst is firing constantly, the rollout buffer fills slowly → fewer updates.

## 8. Loaded checkpoint vs current architecture
- `_load()` does `self.ac.load_state_dict(ck['net'])`.
- If `obs_dim` changed (e.g. you toggled `trend_features`), shapes won't match → silent error or crash.
- **Fix**: check that the checkpoint matches the current `obs_dim`; if not, train fresh.

## 9. Train mode vs eval mode
- `if not self.train: self.ac.eval()` → dropout/BN go to eval, but PPO doesn't use them.
- However, `Categorical.sample()` is still stochastic in eval — by design for exploration, but in deployment you may want greedy:
  ```python
  a_idx = int(logits.argmax())  # greedy
  ```

## 10. NaNs
- Watch for `NaN` in `state` (often from `getRTp95()` returning 0 → division).
- `setpoint = sla * st`; if `st=0` (auto-tuned too low), `lat_ratio` blows up.

## Quick sanity test
```python
from controllers.ppocontroller import PPOController
import numpy as np
c = PPOController(period=1, init_cores=2, train=False)
# Mock monitoring
class M:
    def getRTp95(self): return 0.5
    def getRT(self): return 0.5
    def getQueueLen(self): return 10
    def getArrivalRate(self): return 100
c.monitoring = M()
c.setSLA(1.0)
c.control(t=1.0)
print(c.cores)  # should be in [min_cores, max_cores]
```
