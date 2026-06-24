#!/bin/bash
# Rigorous local μ / p95-floor calibration (amd64 emulation aware).
# Block A: μ(c) homogeneity sweep at ρ≈0.6
# Block B: p95(ρ) fit-check at c=6 (M/M/c predicted vs measured)
# Block C: c=7 repeats (boundary CI)
set -uo pipefail
export DOCKER_HOST="unix:///Users/emilio-imt/.docker/run/docker.sock"
cd /Users/emilio-imt/git/RAS-real
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
TS=$(date +%Y%m%d-%H%M%S)
LOG="logs/calib2-${TS}.log"
COMMON="--hosts http://localhost:8080 http://localhost:8081 --path / --container graph_set --quota-container graph_quota --payload-size 25000 --app-sla 0.25 --wait-time 1 --duration 240 --warmup 30"
echo "CALIB2 START $TS" | tee "$LOG"

run() { # $1=tag $2=cores $3=users
  echo "=== $1 cores=$2 users=$3 ===" | tee -a "$LOG"
  $PY tools/calibrate_mu.py $COMMON --cores "$2" --users "$3" 2>&1 \
    | grep -E "^\[calibrate\] c=" | tee -a "$LOG"
}

# Block A — μ(c) at ρ≈0.6  (users ≈ 9·c)
for c in 2 3 4 5 6 7; do run "A" "$c" "$((9*c))"; done

# Block B — p95(ρ) fit-check at c=6  (ρ≈0.27..0.77)
for u in 27 40 54 67 76; do run "B" 6 "$u"; done

# Block C — c=7 repeats (boundary CI)
for rep in 1 2; do run "C-rep$rep" 7 63; done

echo "CALIB2 DONE $TS" | tee -a "$LOG"
echo "LOGFILE=$LOG"
