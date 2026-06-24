#!/bin/bash
# Scenario A (step, N=0.8) smoke — B0/B1/B3 sequential. Go/no-go on C1/C2 + recover.
set -uo pipefail
export DOCKER_HOST="unix:///Users/emilio-imt/.docker/run/docker.sock"
cd /Users/emilio-imt/git/RAS-real
pkill -f "locust --headless" 2>/dev/null; sleep 2
LC=.venv/bin/locust
TS=$(date +%Y%m%d-%H%M%S)
echo "SMOKE-A START $TS"
for ctrl in ppo mmcpi handover; do
  F="locustfiles/exp-local-smoke-A-${ctrl}.py"
  LOG="logs/smokeA-${ctrl}-${TS}.log"
  echo "=== RUN A ${ctrl} start $(date +%H:%M:%S) → $LOG ==="
  $LC --headless -f "$F" > "$LOG" 2>&1
  echo "=== RUN A ${ctrl} END $(date +%H:%M:%S) rc=$? ==="
  sleep 8
done
echo "SMOKE-A ALL DONE $TS"
ls -dt experiments/exp-local-smoke-A-* 2>/dev/null | head -3
