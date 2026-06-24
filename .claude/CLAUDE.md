# RAS-real — Project Context for Claude

## Mission
Research framework for autoscaling controllers under workload stress. Active research direction: **GPPPO** — a guardrail layer that wraps a PPO RL controller with a Gaussian Process (uncertainty-aware) and an auxiliary PI controller, to keep SLA compliance under model/concept drift where pure PPO degrades.

Owner: Emilio (researcher, paper in progress on RL guardrails).

## Code map (the parts that matter)
- `controllers/ppocontroller.py` — `PPOController`. Actor-critic MLP, 5 discrete actions `[-2..+2]`, on-policy update every `_ROLLOUT=512` ticks. State = `[lat_ratio, q/100, r/1000, trend_p95, cores_norm]`. Reward = `-|asym_pen_lat|`.
- `controllers/gpppo_controller.py` — `GPPPOController(PPOController)`. Adds GP guardrail (sklearn Matern + WhiteKernel, async-trained in `mp.Process`) and an auxiliary `CTControllerScaleX` (PI). Compensation is **monotone-additive**: `final_cores = ppo_cores + max(0, comp)`.
- `controllers/controltheoretical.py` — `CTControllerScaleX`. PI on `e = 1/setpoint - 1/rt`, stateful via `xc_prec`.
- `controller_loop.py` / `base_experiment.py` — Locust `HttpUser` + `LoadTestShape`, glue between generators, controller, monitoring.
- `monitoring.py` — `Monitoring` (RT, RTp95, queue len, arrival rate, users).
- `request_maker.py` — load injection; **noise is applied here** (see `addNoiseToSize`).
- `experiments/exp-*/config.json` — per-run config (controller class + params, generator, SLA, etc.).
- `locustfiles/*` — Locust orchestration scripts.
- `aws-runner.sh`, `aws-multi-runner.sh` — cloud launch scripts.

## Known issues currently impacting research validity
1. **A1**: `prev_action_ppo` stored as action *index* `{0..4}` instead of *delta cores* `{-2..+2}` → GP input is semantically wrong.
2. **A2**: PI advisor used as if stateless but its integral `xc_prec` persists between calls. When GP is untrusted, `control()` is called twice on the same tick → integral pollution.
3. **A3**: GP target = PI compensation → GP risks being a Bayesian wrapper around PI rather than an independent learner of PPO's error.
4. **A4**: Trust mechanism re-trusts immediately on next tick (buffer never empties) → fallback is effectively single-tick.
5. **Confound**: PPO experiments often use `period=3` while GPPPO uses `period=1`. Unfair comparison.

## Workflow
Use the project's slash commands instead of ad-hoc tool calls:
- `/plan <goal>` — full pipeline: triage → multi-expert panel → codex cross-review.
- `/triage <goal>`, `/expert-panel <topic>`, `/codex-cross-review <file>` — standalone phases.
- `/tdd-cycle <feature>` — red-green-refactor with auto-generated test scaffold.
- `/run-experiment <config.json>` — launch a Locust experiment with proper docker/monitoring setup.
- `/compare-runs <runA> <runB>` — diff metrics between two experiment runs.

## House rules
- **TDD-first** for changes to `controllers/*.py`, `monitoring.py`, `request_maker.py`. Skip TDD for plotting, README edits, config tuning.
- **Test sparingly**: this codebase runs in cloud VMs. Cover *behaviour*, not getters. One test per real bug or invariant; avoid mock-heavy ceremony.
- **Italian** is the user's working language.
- When uncertain about controller invariants, run the relevant `*-debug-checklist` skill.
- Before any non-trivial refactor of a controller, run `/expert-panel` with at least RL + Control Theory experts.
- Treat memory entries about specific code lines as point-in-time observations — verify against current code before acting.
