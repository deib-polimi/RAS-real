#!/bin/bash
# Block D — model-free drift potency + recoverability at SinGen peak (λ=35 users).
# Measures p95 at drifted payloads → c_nominal vs c_drift directly.
set -uo pipefail
export DOCKER_HOST="unix:///Users/emilio-imt/.docker/run/docker.sock"
cd /Users/emilio-imt/git/RAS-real
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
TS=$(date +%Y%m%d-%H%M%S); LOG="logs/calibD-${TS}.log"
COMMON="--hosts http://localhost:8080 http://localhost:8081 --path / --container graph_set --quota-container graph_quota --app-sla 0.25 --wait-time 1 --duration 150 --warmup 25 --users 35"
echo "CALIB-D START $TS (payload=size*(1+N), users=35=SinGen peak)" | tee "$LOG"
run() { echo "=== N=$1 payload=$2 cores=$3 ===" | tee -a "$LOG"
  $PY tools/calibrate_mu.py $COMMON --payload-size "$2" --cores "$3" 2>&1 | grep -E "^\[calibrate\] c=" | tee -a "$LOG"; }
# N=0 (nominal): find c_nominal
for c in 3 4 5; do run 0.0 25000 "$c"; done
# N=0.8: find c_drift
for c in 5 6 7; do run 0.8 45000 "$c"; done
# bounds
run 0.5 37500 6
run 1.0 50000 7
echo "CALIB-D DONE $TS"; echo "LOGFILE=$LOG"
