# Azure 32-core Playbook — PPO action-rate failure under sudden load jumps

**Goal.** Show that a frozen reactive PPO (bounded ±2 cores/tick + p95-window lag)
**cannot keep up with a sudden, pronounced LOAD jump at scale**, producing a large
*transient* SLA violation, while a feedforward physics controller (M/M/c from λ̂)
jumps to the right core count immediately. Locally this was impossible (app capacity
high → core needs ≤7 → ±2/tick always enough). At 32 cores the core jump is large
→ the action-rate limit bites.

**Hypothesis (falsifiable).** On a sudden load step that requires e.g. 3→20 cores:
- PPO: transient with high violation **area** and long **settling time** (it crawls
  up at ±2/tick after a ~15-30s window lag).
- MMC-PI / Handover: short settling time (feedforward jumps to the target).
- If PPO settles as fast as the physics → hypothesis falsified → necessity is in
  GUARANTEES, not transient performance. Report honestly either way.

**Metric (NOT average).** `settling_time` (s to bring p95<SLA and keep it) and
`violation_area = ∫ max(0, p95(t)-SLA) dt` over the transient. (= the TCC 2024
settling-time framing.) Average violation% is secondary.

---

## ⚠️ CRITICAL GOTCHAS (read first)

1. **App core ceiling = `uwsgi -p`.** The default `utils/start_graph_app.sh` uses
   `-p 15` → app caps at ~16 cores. **Relaunch with `-p 24`** (Phase 0) or 32 cores
   buys you nothing.
2. **`max_cores=24`** (not 32): leave ~8 cores for locust + controller + OS.
   `controller_loop` pins the quota container to core `max_cores-1`.
3. **Retrain PPO at scale** (Phase 2). Do NOT reuse `local-sin-A`.
4. **Recalibrate** (Phase 1). Azure is native x86 (no emulation) → μ higher, p95
   tails smaller than the Mac. Local numbers (μ≈13, SLA 0.25) do NOT transfer.
5. **`spawn_rate` high** for the jump to be *sudden* (Locust adds users at
   `spawn_rate`/s; default 1 → a "jump" is a slow ramp). Use `spawn_rate=200`.
6. **DOCKER_HOST**: on a Linux VM the socket is the standard `/var/run/docker.sock`
   → the docker SDK works without `DOCKER_HOST`. If `controller_loop`/`calibrate_mu`
   error on docker connection, `export DOCKER_HOST=unix:///var/run/docker.sock`.

---

## Phase 0 — Setup (remote 32-core Azure VM, Ubuntu)

```bash
# system deps
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip git docker.io curl
sudo systemctl enable --now docker && sudo usermod -aG docker $USER && newgrp docker

# repo + venv
cd ~ && git clone <REPO_URL> RAS-real && cd RAS-real && git checkout guardrail && git pull
python3.12 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install locust torch numpy scipy docker requests matplotlib

# launch app WITH MORE WORKERS (the key change for 32 cores)
FIXED="$PWD/utils/web_server_graph_mst_fixed.py"
docker rm -f graph_set graph_quota 2>/dev/null || true
docker run --name graph_set  -d -p 8080:8080 -v "$FIXED:/usr/src/app/web_server_graph_mst.py:ro" \
   systemautoscaler/sebs-dynamic_html:0.0.1 uwsgi --http 0.0.0.0:8080 --master -p 24 -w web_server_graph_mst:app
docker run --name graph_quota -d -p 8081:8080 -v "$FIXED:/usr/src/app/web_server_graph_mst.py:ro" \
   systemautoscaler/sebs-dynamic_html:0.0.1 uwsgi --http 0.0.0.0:8080 --master -p 1  -w web_server_graph_mst:app

# sanity
docker exec graph_set grep -q request.get_json /usr/src/app/web_server_graph_mst.py && echo "patch OK"
for p in 8080 8081; do curl -s -X POST localhost:$p/ -H 'Content-Type: application/json' -d '{"size":25000}' -w " http=%{http_code} t=%{time_total}s\n" -o /dev/null; done
nproc   # confirm 32
```

---

## Phase 1 — Calibration at scale (~30 min)

Edit `tools/calibration_run.sh` (or run inline) to sweep the larger core range:

```bash
# inline calibration sweep at scale (ρ≈0.6, users≈0.6·c·μ_guess; start μ_guess≈15)
for c in 2 4 8 12 16 20 23; do
  u=$(python3 -c "print(round(9*$c))")
  .venv/bin/python tools/calibrate_mu.py --hosts http://localhost:8080 http://localhost:8081 \
    --path / --container graph_set --quota-container graph_quota \
    --cores $c --users $u --duration 180 --warmup 30 --payload-size 25000 --app-sla 0.25 --wait-time 1
done 2>&1 | grep -E "^\[calibrate\] c="
```

**Read off and record:**
- `μ_eff` per core (≈ median μ_fit across c). Call it **MU**.
- p95 floor at ρ≈0.6 → set **SLA** = ~2× the p95 floor (generous, so nominal never
  violates). Likely lower than the Mac's 0.25 (native x86 faster).
- **Capacity** ≈ `23 · MU` req/s. Max recoverable λ ≈ `0.7 · 23 · MU`.

**Derive the jump sizing** (fill into Phase 3):
- `LAM_LO` (nominal) ≈ such that nominal needs ~3-4 cores: `LAM_LO ≈ 3.5·MU·0.7`.
- `LAM_HI` (post-jump) ≈ needs ~20 cores, still recoverable: `LAM_HI ≈ 20·MU·0.7`
  (cap at `0.7·23·MU`). The bigger `LAM_HI - LAM_LO` (in CORES), the harder the
  action-rate failure.

---

## Phase 2 — Train PPO at scale (~1-3 h, overnight)

The PPO must be in-distribution for BOTH `LAM_LO` and `LAM_HI` *levels*, so the only
thing it has never seen is the *sudden transition* → isolates the action-rate failure
(not an OOD-level artifact). Train on a SinGen that spans `[LAM_LO, LAM_HI]`.

Create `locustfiles/exp-azure-train-ppo.py` (copy `exp-local-train-ppo-sin.py`, then):
- generator `SinGen(mod=(LAM_HI-LAM_LO)/2, shift=(LAM_HI+LAM_LO)/2, period=360)`
- `app_sla=<SLA>`, `max_cores=24`, `cpu_range_start=0`, `period=1`, `cost_coef=0.02`
- `noise_scale=0.0` (no service drift during training), `train=True`,
  `model_suffix="azure-scale"`, `end=10800` (3h) or `18000` (5h).

```bash
nohup .venv/bin/locust --headless -f locustfiles/exp-azure-train-ppo.py > logs/train-azure.log 2>&1 &
tail -f logs/ppo-none-*.log    # watch: std(cores)>1, argmax settling on Δ0/+1, reward sensing violations
```
Checkpoint: `controllers/ppocontroller-none-azure-scale.pt`. Sanity: in a no-drift
eval it should give ~0% violations (in-distribution competent — gate T1).

---

## Phase 3 — The failure experiments (load jumps)

Add scenarios to `smoke_common.py` (the remote Claude can do this) — or new
locustfiles. Common block: `app_sla=<SLA>`, `max_cores=24`, `period=1`,
`monitoring_window=30`, `model_suffix="azure-scale"`, `spawn_rate=200`,
`container_ids=[graph_set,graph_quota]`, MMC-PI/Handover `mu_window_s=30`.
**noise_scale=0** (this is a LOAD experiment, not service-time).

### E1 — Sudden load STEP (headline)
Generator `StepGen(intervals=[300, 999999], values=[LAM_LO, LAM_HI])`, `end=900`,
`spawn_rate=200`. Run the triad:
```bash
for ctrl in ppo mmcpi handover; do
  .venv/bin/locust --headless -f locustfiles/exp-azure-E1-${ctrl}.py 2>&1 | tee logs/E1-${ctrl}.log
done
```
Expected: PPO crawls 3→20 at ±2/tick after window lag → big transient; physics jumps.

### E2 — Fast load RAMP (robustness)
Generator `RampGen(slope=20, steady=320, initial=LAM_LO, rampstart=300)` (20 users/s
for ~1s span; with spawn_rate=200 the actuation follows). Same triad.

### E3 (optional) — real bursty trace at scale
`WikiGen(shift=10, bias=<LAM_HI>)` (burstiness 2.08×). Stress test of repeated spikes.

Run order: **E1 first** (clearest). If PPO fails on E1, run E2/E3 + multi-seed.

---

## Phase 4 — Analysis (transient metrics)

```bash
.venv/bin/python tools/analyze_transient.py --glob "experiments/exp-azure-E1-*/data.mat" --sla <SLA> --drift 300
```
Reports per controller: settling_time, violation_area, peak p95, cores trajectory.
**Necessity demonstrated if**: PPO settling_time and violation_area ≫ MMC-PI/Handover,
with PPO recovering eventually (transient, not saturation). Then: ≥5 seeds for stats.

---

## Acceptance / honest stop conditions
- ✅ **Found**: PPO violation_area ≥ 3× physics AND settling_time ≥ 2× physics, with
  the jump recoverable (post-jump load ≤ 0.7·23·MU). → run multi-seed, write it up on
  settling-time.
- ❌ **Not found** (PPO settles ~as fast): the action-rate limit isn't binding even at
  scale (or the closed-loop bounds it) → pivot to the GUARANTEES framing (provable
  M/M/c floor), and consider an open-loop workload as the next lever.

## Notes for the remote Claude Code instance
- This repo's `smoke_common.py` already has the fairness-by-construction pattern
  (COMMON + SCENARIOS + CONTROLLERS); extend it with E1/E2/E3 scenarios + a `_STAT`/
  `_STEP`/`_RAMP` generator and 24-core `_CTRL_COMMON` (init_cores≈3, max_cores=24).
- `MuEstimator(window_s=30)` (in `mmc_pi_controller.py`) is the fast μ̂ — keep it.
- Keep all baselines IDENTICAL except the controller (run `make_config` fairness check).
