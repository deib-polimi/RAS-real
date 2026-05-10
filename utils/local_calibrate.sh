#!/usr/bin/env bash
# utils/local_calibrate.sh
#
# 4-phase local calibration pipeline:
#   PHASE 1 — capability discovery (host + Docker VM)
#   PHASE 2 — container lifecycle (teardown + bring-up + readiness)
#   PHASE 3 — μ calibration via tools/calibrate_mu.py
#   PHASE 4 — auto-generate locustfiles/exp-local-bidirect.py with calibrated knobs
#
# Designed for the H4 in-vitro experiment (gp_buffer_reset_at).
# Run from anywhere — the script chdirs to the repo root.

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$REPO_ROOT"

# Docker SDK fix: docker.from_env() in tools/calibrate_mu.py defaults to
# /var/run/docker.sock, which doesn't exist on macOS Docker Desktop (the real
# socket is at ~/.docker/run/docker.sock). Auto-detect via docker CLI's
# context system and export DOCKER_HOST so the python SDK uses the right path.
# On Linux EC2 the default socket exists → this is a no-op there.
if [ -z "${DOCKER_HOST:-}" ]; then
    DOCKER_HOST_DETECTED=$(docker context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null || true)
    if [ -n "$DOCKER_HOST_DETECTED" ]; then
        export DOCKER_HOST="$DOCKER_HOST_DETECTED"
        echo "Detected DOCKER_HOST=$DOCKER_HOST (for Python docker SDK)"
    fi
fi

# ---------------------------------------------------------------------------
# PHASE 1 — Capability discovery
# ---------------------------------------------------------------------------
echo "=== PHASE 1: Capability discovery ==="
echo "Host:"
echo "  arch:        $(uname -m)"
echo "  kernel:      $(uname -s) $(uname -r)"
if [[ "$(uname -s)" == "Darwin" ]]; then
    echo "  logical CPU: $(sysctl -n hw.logicalcpu)"
    echo "  physical CPU: $(sysctl -n hw.physicalcpu)"
    HOST_RAM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
    echo "  RAM:         ${HOST_RAM_GB} GB"
fi

if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon not reachable. Start Docker Desktop and retry."
    exit 1
fi

echo "Docker VM:"
DOCKER_VCPU=$(docker run --rm alpine nproc 2>/dev/null)
DOCKER_RAM_KB=$(docker run --rm alpine sh -c 'grep MemTotal /proc/meminfo' | awk '{print $2}')
DOCKER_ARCH=$(docker run --rm alpine uname -m)
DOCKER_RAM_MB=$(( DOCKER_RAM_KB / 1024 ))
echo "  vCPU:        $DOCKER_VCPU"
echo "  RAM:         ${DOCKER_RAM_MB} MB"
echo "  arch:        $DOCKER_ARCH"

if [ "$DOCKER_VCPU" -lt 2 ]; then
    echo "ERROR: Docker VM has only $DOCKER_VCPU vCPU; need ≥2 to test scaling."
    echo "  Increase 'CPUs' in Docker Desktop → Settings → Resources, then retry."
    exit 1
fi

# ---------------------------------------------------------------------------
# PHASE 2 — Container lifecycle
# ---------------------------------------------------------------------------
# Local note: the WSGI app inside the container exposes POST on `/` only
# (the `/function/graph_mst` route is commented in /usr/src/app/web_server_graph_mst.py).
# On AWS that path works because of OpenFaaS gateway rewrite or a different
# image build; we don't replicate that here — the local config will use `/`.
# A `/health` endpoint exists and is the cleanest readiness probe.
echo ""
echo "=== PHASE 2: Container lifecycle ==="

# Skip bring-up if both containers are already healthy.
SKIP_BRINGUP=0
if curl -fsS http://localhost:8080/health -o /dev/null --max-time 2 2>/dev/null \
    && curl -fsS http://localhost:8081/health -o /dev/null --max-time 2 2>/dev/null; then
    SKIP_BRINGUP=1
    echo "Both containers already healthy → skipping teardown + bring-up."
fi

if [ "$SKIP_BRINGUP" -eq 0 ]; then
    echo "Teardown previous containers (idempotent)..."
    docker rm -f graph_set graph_quota graph_mount_test >/dev/null 2>&1 || true

    echo "Starting graph_set + graph_quota via utils/start_graph_app.sh..."
    bash utils/start_graph_app.sh

    echo "Waiting for /health readiness (up to 30s)..."
    READY=0
    for i in $(seq 1 15); do
        if curl -fsS http://localhost:8080/health -o /dev/null --max-time 3 2>/dev/null \
            && curl -fsS http://localhost:8081/health -o /dev/null --max-time 3 2>/dev/null; then
            READY=1
            echo "  both containers responsive after ${i}×2s"
            break
        fi
        sleep 2
    done

    if [ "$READY" -eq 0 ]; then
        echo "ERROR: containers did not become ready within 30s"
        docker ps -a | grep -E 'graph_set|graph_quota' || true
        docker logs graph_set 2>&1 | tail -20 || true
        docker logs graph_quota 2>&1 | tail -20 || true
        exit 1
    fi
fi

# Final functional sanity: POST / must return 200 (the actual workload path).
if ! curl -fsS -X POST http://localhost:8080/ \
        -H "Content-Type: application/json" -d '{"size":1000}' \
        -o /dev/null --max-time 5; then
    echo "ERROR: POST / on graph_set did not return success — workload path unreachable"
    exit 1
fi
echo "Functional sanity OK: POST / returns 2xx"

# ---------------------------------------------------------------------------
# PHASE 3 — μ calibration
# ---------------------------------------------------------------------------
echo ""
echo "=== PHASE 3: μ calibration ==="

# Build cores list = base[≤vCPU] ∪ {vCPU}
CORES_LIST=()
for c in 1 2 4 8 16; do
    if [ "$c" -le "$DOCKER_VCPU" ]; then
        CORES_LIST+=("$c")
    fi
done
INCLUDED=0
for c in "${CORES_LIST[@]}"; do
    if [ "$c" -eq "$DOCKER_VCPU" ]; then
        INCLUDED=1
    fi
done
if [ "$INCLUDED" -eq 0 ]; then
    CORES_LIST+=("$DOCKER_VCPU")
fi

echo "Calibration plan: cores=${CORES_LIST[*]}  users=22  duration=300s/point  warmup=15s/point"
TOTAL_MIN=$(( (${#CORES_LIST[@]} * (300 + 15 + 5)) / 60 ))
echo "Estimated wall time: ~${TOTAL_MIN} min"

if ! python3 -c "import docker, requests" 2>/dev/null; then
    echo "ERROR: missing python deps — install with:  pip3 install docker requests"
    exit 1
fi

python3 tools/calibrate_mu.py \
    --hosts http://localhost:8080 http://localhost:8081 \
    --container graph_set --quota-container graph_quota \
    --path / \
    --cores "${CORES_LIST[@]}" \
    --users 22 \
    --duration 300 --warmup 15 \
    --payload-size 25000 --app-sla 0.25

# ---------------------------------------------------------------------------
# PHASE 4 — Auto-generate exp-local-bidirect.py
# ---------------------------------------------------------------------------
echo ""
echo "=== PHASE 4: Auto-generate exp-local-bidirect.py ==="

LATEST_JSON=$(ls -t tools/calibrate_mu_*.json 2>/dev/null | head -1)
if [ -z "${LATEST_JSON:-}" ] || [ ! -f "$LATEST_JSON" ]; then
    echo "ERROR: no tools/calibrate_mu_*.json produced — calibration must have failed."
    exit 1
fi
echo "Reading calibration: $LATEST_JSON"

read INIT_C MAX_C LAM MU <<<"$(python3 - "$LATEST_JSON" <<'PYEOF'
import json, sys, math
data = json.load(open(sys.argv[1]))
results = data["results"]
sla = float(data["args"]["app_sla"])
tested = [r for r in results if r.get("n", 0) > 0]
if not tested:
    print("0 0 0 0.0")
    sys.exit(0)
max_r = max(tested, key=lambda r: r["c"])
max_c = int(max_r["c"])
in_sla = sorted((r for r in results
                 if r.get("mean_rt") is not None and r["mean_rt"] < sla),
                key=lambda r: r["c"])
init_c = int(in_sla[0]["c"]) if in_sla else max(2, max_c // 2)
mu = max_r.get("mu_fit_per_core") or 1.0
lam = max(2, int(round(0.7 * mu * max_c)))
print(init_c, max_c, lam, f"{mu:.3f}")
PYEOF
)"

if [ -z "$MAX_C" ] || [ "$MAX_C" = "0" ]; then
    echo "ERROR: calibration produced no usable measurements."
    exit 1
fi

NOISE_START=300
END=600
GP_RESET_AT=$NOISE_START

echo "Calibrated knobs:"
echo "  init_cores       = $INIT_C  (smallest tested c with mean_RT < SLA)"
echo "  max_cores        = $MAX_C   (largest c tested successfully)"
echo "  lam              = $LAM   (closed-loop users → ρ_pre ≈ 0.7)"
echo "  μ_eff/core       = $MU req/s"
echo "  noise_start      = $NOISE_START"
echo "  end              = $END"
echo "  gp_buffer_reset_at = $GP_RESET_AT (= noise_start)"

OUT=locustfiles/exp-local-bidirect.py
cat > "$OUT" <<PYFILE
"""Local bidirect-GP run — AUTO-GENERATED by utils/local_calibrate.sh.

LOCAL ONLY — DO NOT RUN ON AWS as-is. The request path is "/" because the
locally-launched uwsgi container exposes the workload on root (its
/function/graph_mst route is commented in the source). On AWS the path
"/function/graph_mst" works through a different routing path.

Calibrated for this machine:
  Docker vCPU       = $DOCKER_VCPU
  μ_eff @ c=$MAX_C  = $MU req/s/core   (M/M/c fit)
  capacity          = μ · max_cores = $(python3 -c "print(round($MU * $MAX_C, 1))") req/s
  pre-drift  ρ      ≈ 0.7  (lam=$LAM, μ·max=$(python3 -c "print(round($MU * $MAX_C, 1))"))
  post-drift ρ      ≈ 0.91 (= 0.7 · noise_scale=1.3)  → drift saturates without imploding

Hypothesis under test: H4 — GP training buffer is poisoned by a pre+post-drift
mix, leading to a degenerate fit that fails to extrapolate post-drift OOD.
With \`gp_buffer_reset_at = noise_start\` we wipe the buffer at the known drift
onset, giving the GP a clean post-drift-only training set.

If H4 is the dominant cause, the post-drift cascade observed at t≈300-365 in
the AWS bidirect run should disappear and tail latency should drop toward the
PPO baseline level.
"""

CONFIG = {
    "hosts": ["http://localhost:8080", "http://localhost:8081"],
    "containerIds": ["graph_set", "graph_quota"],
    "request": {
        "method": "POST",
        "data": {"size": 25000},
        "headers": {"Content-Type": "application/json"},
        # LOCAL: workload exposed on root path (no OpenFaaS gateway here).
        "path": "/",
    },
    "cpu_range_start": 0,
    "monitoring_window": 30,
    "app_sla": 0.25,
    "wait_time_min": 1,
    "wait_time_max": 1,
    "spawn_rate": 1,

    "end": $END,

    # Drift: step at t=$NOISE_START, persistent until end.
    "noise_start": $NOISE_START,
    "noise_scale": 1.3,
    "noise_type": "avg",
    "noise_drift_kind": "step",
    "noise_drift_end": $END,
    "noise_drift_period": $NOISE_START,
    "seed": 42,

    "generator": {
        "class": "StationaryGen",
        "params": {"lam": $LAM},
    },

    "controller": {
        "class": "GPPPOController",
        "params": {
            "period": 1,
            "init_cores": $INIT_C,
            "min_cores": 1.0,
            "max_cores": $MAX_C,
            "st": 1.0,
            "st_max": 1.0,
            "min_st": 1.0,
            "train": False,
            "deterministic_eval": True,
            "burst_mode": "none",
            "trend_features": False,
            "enable_log": True,
            "log_dir": "./logs",

            # PI muted — guardrail is GP-only
            "bc": 0.0,
            "dc": 0.0,
            "pi_anti_windup": False,
            "pi_e_clip": 10.0,
            "pi_error_form": "linear",
            "pi_rt_deadband_frac": 0.30,

            # GP scheduling
            "gp_train_start": 10,
            "gp_min_samples": 30,
            "gp_train_freq": 50,
            "gp_max_buffer_size": 500,
            "pi_start_time": 5,
            "gp_time_period": 200,
            "gp_async": True,

            # B1: bidirectional guardrail
            "gp_target_mode": "signed_shortfall",
            "gp_percentile": 50,
            "gp_normalize_inputs": True,
            "gp_trust_mode": "outcome",
            "gp_distrust_dwell": 0,

            # Lookahead disabled in signed mode
            "gp_lookahead_horizon": 0,
            "gp_adaptive_train": False,
            "gp_drift_threshold": 1.5,
            "gp_min_train_interval": 10,
            "gp_eviction_keep": 0,

            # H4 in-vitro — hard-reset GP at known drift onset
            "gp_buffer_reset_at": $GP_RESET_AT,
        },
    },
}


EXP_NAME = __file__.split("/")[-1].split(".")[0]

from base_experiment import *
setup(EXP_NAME, CONFIG)
PYFILE

echo "Generated: $OUT"
echo ""
echo "=== ALL DONE ==="
echo ""
echo "Containers are still up. Inspect with:  docker ps | grep graph_"
echo "Tear down with:                         docker rm -f graph_set graph_quota"
echo ""
echo "Run the local bidirect experiment:"
echo "  locust -f $OUT --headless 2>&1 | tee bidirect-local.log"
echo ""
echo "Then parse with the same parser used for AWS:"
echo "  python3 /tmp/parse_logs.py  # (point ROOT at this repo)"
