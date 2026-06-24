# Reproducing the PPO+Guardrail experiments on AWS

End-to-end recipe to replicate the paper experiments on a cloud VM with
more cores than a typical laptop (≥16 vCPU recommended). The pipeline is:

```
[AWS setup] → [calibration] → [scenario sizing] → [PPO training] → [A/B test] → [analysis]
```

All steps assume you run on a fresh **Ubuntu 22.04** EC2 instance (or
equivalent). Tested on `c7i.4xlarge` (16 vCPU x86) and `c7g.4xlarge`
(16 vCPU ARM Graviton3). Total wall-clock ≈ 5-7 hours.

---

## 0. Recommended hardware

| Instance | vCPU | Arch | On-demand $/h | Spot $/h | Notes |
|---|---|---|---|---|---|
| `c7i.4xlarge` | 16 | x86 | ~$0.85 | ~$0.25 | Default safe choice |
| `c7g.4xlarge` | 16 | ARM | ~$0.58 | ~$0.17 | Best price, verify Docker image arch |
| `c7i.8xlarge` | 32 | x86 | ~$1.70 | ~$0.50 | Extra headroom for severe drift sweep |

`max_cores=16` is enough for `noise_scale ≤ 2.0`. For `noise_scale=3.0+`
use 32 vCPU.

---

## 1. Connect + bootstrap

```bash
ssh -i ~/your-key.pem ubuntu@<EC2_PUBLIC_DNS>

# System packages
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip git docker.io curl

# Docker permissions
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
newgrp docker

# Sanity check
docker --version
docker run --rm hello-world
```

---

## 2. Clone repo + Python env

```bash
cd ~
git clone https://github.com/<your-org>/RAS-real.git
cd RAS-real
git checkout guardrail

python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install locust torch numpy scipy docker requests matplotlib
# If a requirements.txt is present:
[ -f requirements.txt ] && pip install -r requirements.txt
```

---

## 3. Start the workload containers

```bash
bash utils/start_graph_app.sh

# Verify both containers are running
docker ps --format '{{.Names}}: {{.Status}}' | grep graph

# Probe both endpoints
for port in 8080 8081; do
  curl -s -X POST http://localhost:$port/ \
    -H 'Content-Type: application/json' -d '{"size":25000}' \
    -w "  http=%{http_code} t=%{time_total}s\n" -o /dev/null
done
```

Expected: both endpoints return HTTP 200 in <100ms.

---

## 4. Adapt `max_cores` and the calibration schedule for the host

The Mac-tuned locustfiles use `max_cores=8`. Bump to 16 for the AWS box:

```bash
sed -i 's/"max_cores": 8/"max_cores": 16/g' \
    locustfiles/exp-local-calibrate.py \
    locustfiles/exp-local-train-ppo-sin.py \
    locustfiles/exp-local-ppoonly-sin-ood.py \
    locustfiles/exp-local-handover-sin-ood.py
```

Extend the calibration schedule to cover the wider core range. Open
`locustfiles/exp-local-calibrate.py` and replace the `SCHEDULE` block:

```python
# Calibration schedule for 16-core host (lam ≈ 0.75 · c · μ̂_expected)
SCHEDULE = [
    (   0,  2,  24),   # 30s warmup + 600s measure per slot
    ( 630,  4,  48),
    (1260,  8,  96),
    (1890, 12, 144),
    (2520, 16, 192),
]
END = 3150           # 5 × 630s
```

The schedule values `lam` are sized assuming μ̂ ≈ 12 req/s/core. After the
first calibration, you'll get the actual μ̂ for this host and you may
re-tune. The acceptable region is ρ ∈ [0.5, 0.8] per slot, which is wide
enough that a first pass with these defaults is good.

---

## 5. Calibration (≈ 52 min)

```bash
locust --headless -f locustfiles/exp-local-calibrate.py 2>&1 \
  | tee logs/calibrate-aws-$(date +%Y%m%d-%H%M%S).log
```

When done, generate the report:

```bash
python3 tools/parse_calibration.py \
    "$(ls -t logs/calibration-*.jsonl | head -1)" \
    --warmup-s 30 \
    --noise-scale-target 1.5 \
    --max-cores 16 \
    --sla-min-ms 100
```

The report prints Markdown to stdout and saves a JSON next to the JSONL.
Read the **Recommendations** section: it gives you the **SLA** in
milliseconds and the **SinGen** parameters (`shift`, `mod`, `period`) sized
for the measured per-core service rate.

---

## 6. Apply the calibrated parameters to the training/test locustfiles

Take the numbers from the calibration report and substitute them. Example
(values are illustrative — use yours):

```bash
# From the calibration report:
NEW_SLA=0.18         # Recommendations → SLA proposed (seconds)
NEW_MOD=25           # Recommendations → SinGen mod
NEW_SHIFT=45         # Recommendations → SinGen shift
NEW_SUFFIX="aws-sin" # any unique tag; will produce ppocontroller-none-aws-sin.pt

python3 - <<PY
import re
files = [
    'locustfiles/exp-local-train-ppo-sin.py',
    'locustfiles/exp-local-ppoonly-sin-ood.py',
    'locustfiles/exp-local-handover-sin-ood.py',
]
for f in files:
    c = open(f).read()
    c = re.sub(r'"app_sla":\s*[\d.]+', f'"app_sla": {$NEW_SLA}', c)
    c = re.sub(r'"mod":\s*[\d.]+',     f'"mod": {$NEW_MOD}', c)
    c = re.sub(r'"shift":\s*[\d.]+',   f'"shift": {$NEW_SHIFT}', c)
    c = re.sub(r'"model_suffix":\s*"[^"]+"', '"model_suffix": "$NEW_SUFFIX"', c)
    open(f, 'w').write(c)
    print(f"updated: {f}")
PY
```

(If you prefer, just open the three files in an editor and update the four
fields by hand; it is faster and less error-prone for one-off changes.)

---

## 7. Train PPO with the calibrated SinGen workload

Default `end=10800` (3h). For an overnight 5h run:

```bash
sed -i 's/"end": 10800/"end": 18000/' locustfiles/exp-local-train-ppo-sin.py
```

Launch in background and tail the PPO log:

```bash
nohup locust --headless -f locustfiles/exp-local-train-ppo-sin.py 2>&1 \
  | tee logs/train-aws-sin-$(date +%Y%m%d-%H%M%S).log > /dev/null &

# Watch the PPO controller log live
tail -f logs/ppo-none-2026*.log
```

PPO rollout = 512 ticks; expect one update every ~512s. 3h → ~21 updates.
5h → ~35 updates. The checkpoint is overwritten on every update at
`controllers/ppocontroller-none-<NEW_SUFFIX>.pt`.

Sanity checks during training (any time):

```bash
# Policy bias — should NOT collapse to argmax=Δ=-2 with very negative asymmetry
.venv/bin/python -c "
import torch
ck = torch.load('controllers/ppocontroller-none-aws-sin.pt', map_location='cpu', weights_only=False)
b = ck['net']['policy_head.bias'].numpy()
print(f'step_cnt={ck[\"steps\"]}')
print(f'bias = {b}')
print(f'asymm (+2)-(-2) = {b[4]-b[0]:+.4f}')
print(f'argmax = Δ={[-2,-1,0,1,2][b.argmax()]:+d}')
"
```

A healthy training shows `std(cores)` rising above 1, `argmax` settling on
`Δ=0` or `Δ=+1`, and reward in `last100` ticks more negative than the
first 100 (PPO has started to sense violations).

---

## 8. Paired A/B test (≈ 15 min each, run sequentially)

### A — PPO only (no guardrail)

```bash
locust --headless -f locustfiles/exp-local-ppoonly-sin-ood.py 2>&1 \
  | tee logs/ppoonly-aws-$(date +%Y%m%d-%H%M%S).log
```

### B — PPO + handover guardrail

```bash
locust --headless -f locustfiles/exp-local-handover-sin-ood.py 2>&1 \
  | tee logs/handover-aws-$(date +%Y%m%d-%H%M%S).log
```

Both files share the SinGen workload, the drift step at `t=400`
(`noise_scale=1.5`), and the trained `.pt`. The only structural difference
is the controller class.

---

## 9. Compare A vs B

```bash
.venv/bin/python <<'PY'
from scipy.io import loadmat
import numpy as np, glob
SLA = 0.18   # ← use the value you set in step 6

for label, pattern in [
    ('PPO-only A', 'experiments/exp-local-ppoonly-sin-ood-*/data.mat'),
    ('Handover B', 'experiments/exp-local-handover-sin-ood-*/data.mat'),
]:
    path = sorted(glob.glob(pattern))[-1]
    d = loadmat(path)
    rts = np.array(d['rts']).flatten()
    times = np.array(d['time']).flatten()
    cores = np.array(d['cores']).flatten()
    print(f'=== {label}: {path}')
    for ph, m in [
        ('PRE-DRIFT  ', (times>=30) & (times<=400)),
        ('DRIFT-EARLY', (times>400) & (times<=450)),
        ('DRIFT-STABLE',(times>450)),
    ]:
        rt = rts[m]; c = cores[m]
        if len(rt) == 0: continue
        viol = 100*(rt>SLA).sum()/len(rt)
        print(f'  {ph}: N={len(rt):4d} '
              f'rt_mean={rt.mean():.3f}s max={rt.max():.3f}s '
              f'cores={c.mean():.2f} viol_mean={viol:.1f}%')
    print()
PY
```

What to look for:

* **Pre-drift**: both A and B should be deeply below SLA (`viol < 5%`),
  `cores` adapted to the SinGen midline.
* **Drift-early (transient ~50s)**: both spike. B may briefly look worse
  because the handover transition adds settling time.
* **Drift-stable** (the headline number for the paper):
  * `rt_mean A` vs `rt_mean B`: how much guardrail recovers the mean.
  * `viol_mean`: handover should be ≥ 30% lower.
  * `cores B > cores A`: guardrail spent more cores to recover.

---

## 10. Optional: drift severity sweep

To show the safe-operation envelope, repeat steps 8 + 9 with several
`noise_scale` values (edit the two test locustfiles each time):

```
noise_scale ∈ {0.5, 1.0, 1.5, 2.0, 3.0}
```

Expected outcomes:

* `0.5–1.0`: A recovers in mean; guardrail adds minor improvement.
* `1.5`: A degrades on p95; guardrail recovers the mean.
* `2.0–3.0`: A fails; guardrail spends more cores; recovery quality
  depends on `1/μ_post` vs `SLA` (see [theory](#theory) below).

---

## Theory — when guardrail can recover (and when it cannot)

Post-drift effective service rate (noise_scale = N on payload):

```
μ_post ≈ μ_pre / (1 + N)
1/μ_post  ← floor of mean RT under M/M/c
```

* **Mean recovery feasible** iff `(1+N) · (1/μ_pre) < SLA`.
* **p95 recovery feasible** (rule of thumb p95 ≈ 2·mean) iff
  `2 · (1+N) · (1/μ_pre) < SLA`.

Pick `noise_scale` so the regime you want to study is feasible. The
calibration step gives you `μ_pre`; everything else falls out of those
two inequalities.

---

## Troubleshooting

* **Docker pull is slow on first run**: the `start_graph_app.sh` script
  fetches `systemautoscaler/sebs-dynamic_html:0.0.1` (≈ 200 MB).
* **`cpuset_cpus` rejected**: ensure `max_cores ≤ host cpu_count`. The
  helper functions in `controller_loop.py` pin the quota container to
  CPU `max_cores - 1`.
* **Locust reports 100% failures but containers respond 200**: known
  spurious bookkeeping issue, does **not** affect the `monitoring` /
  reward path. Ignore unless `docker logs graph_set` shows HTTP errors.
* **PPO converges to `cores=1` (collapsed policy)**: verify that
  `ppocontroller.py:_reward` uses `getRTp95()` (Fix A), not `getRT()`.
  The training log should show non-trivial negative `rew` (≈ -0.05) when
  p95 exceeds SLA, not values pinned near `0.000`.
* **`docker stats` poll fails**: the `DockerCPUSampler` thread silently
  retries; first 3 failures are logged, then every 10th.

---

## Cost / time recap

| Phase | Wall-clock | Notes |
|---|---|---|
| Bootstrap (1–3) | ~10 min | One-off |
| Calibration (5) | ~52 min | 5-slot schedule |
| Parameter sync (6) | ~5 min | Manual or scripted |
| Training (7) | 3–5 h | Overnight friendly |
| A/B test (8) | ~30 min | 2 × 15 min |
| Analysis (9) | <1 min | One Python snippet |
| Sweep (10, opt) | +30 min per scenario | Add 5 = 2.5 h |

Total on `c7i.4xlarge` spot (~$0.25/h): **≈ $1.5 – 3** end to end.
