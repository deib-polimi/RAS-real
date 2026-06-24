---
name: experiment-config-validator
description: Validates experiments/exp-*/config.json against the controller and generator signatures before launch. TRIGGER before any /run-experiment call or whenever a new config is created/modified.
---

# Experiment Config Validator

## What a valid config looks like
```json
{
  "app_sla": 1.0,
  "monitoring_window": 30,
  "cpu_range_start": 1,
  "request": { ... },
  "generator": {
    "class": "TweetGen",
    "params": { ... }
  },
  "controller": {
    "class": "GPPPOController",
    "params": {
      "period": 1,
      "init_cores": 2,
      "min_cores": 1,
      "max_cores": 100,
      "st": 0.8,
      "bc": 5.0,
      "dc": 10.0,
      ...
    }
  }
}
```

## Validation rules

### Schema-level
- [ ] `app_sla` exists and `> 0`
- [ ] `monitoring_window` exists and `> 0`
- [ ] `cpu_range_start` exists
- [ ] `controller.class` is a string
- [ ] `controller.params` is an object (can be `{}` for defaults)
- [ ] `generator.class` and `generator.params` present

### Controller resolution
- [ ] `controller.class` resolves: it must be importable from `controllers/` (check `controllers/__init__.py`)
- [ ] All keys in `controller.params` match the controller's `__init__` signature (read the file, list keyword args, diff against keys)
- [ ] No required arg is missing (any keyword arg without default)

### Generator resolution
- [ ] `generator.class` resolves under `generators/`
- [ ] `generator.params` keys match its `__init__` signature

### Sanity checks (warnings, not errors)
- [ ] If `controller.class == "GPPPOController"` and `gp_min_samples > gp_max_buffer_size` → impossible to ever reach training threshold
- [ ] If `period > monitoring_window` → controller fires before monitoring has fresh data
- [ ] If `init_cores > max_cores` or `init_cores < min_cores` → bounds violation
- [ ] If `st * app_sla` (the setpoint) is below 0.05 → likely too aggressive
- [ ] **Fairness watch**: if you're comparing PPO vs GPPPO, both should have the same `period`, `app_sla`, `init_cores`, `min_cores`, `max_cores`, and the same generator config. Surface any mismatch.

## How to validate (programmatically)
```python
import json, inspect, importlib

with open(config_path) as f:
    cfg = json.load(f)

# Resolve controller class
mod = importlib.import_module("controllers")
cls = getattr(mod, cfg["controller"]["class"])
sig = inspect.signature(cls.__init__)
provided = set(cfg["controller"]["params"].keys())
required = {n for n, p in sig.parameters.items()
            if p.default is inspect._empty and n != "self"}
missing = required - provided
extra = provided - set(sig.parameters.keys())
assert not missing, f"missing required params: {missing}"
assert not extra, f"unknown params: {extra}"
```

## Output of a validation run
```
[VALID] experiments/exp-foo/config.json
- Controller: GPPPOController (12 params, all known)
- Generator: TweetGen (3 params, all known)
- Warnings: 1 (period=1 vs PPO baseline period=3 — fairness)
```
or
```
[INVALID] experiments/exp-foo/config.json
- ERROR: controller param "kp" not in GPPPOController.__init__ signature
- ERROR: missing required param "init_cores"
```
