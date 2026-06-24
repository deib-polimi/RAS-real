#!/bin/bash
# Scenario S (StationaryGen λ=35, step, N=0.8) — necessity smoke. B0/B1/B3 sequential.
set -uo pipefail
export DOCKER_HOST="unix:///Users/emilio-imt/.docker/run/docker.sock"
cd /Users/emilio-imt/git/RAS-real
pkill -f "locust --headless" 2>/dev/null; sleep 2
LC=.venv/bin/locust
TS=$(date +%Y%m%d-%H%M%S)
echo "SMOKE-S START $TS"
for ctrl in ppo mmcpi handover; do
  F="locustfiles/exp-local-smoke-S-${ctrl}.py"
  echo "=== RUN S ${ctrl} start $(date +%H:%M:%S) ==="
  $LC --headless -f "$F" > "logs/smokeS-${ctrl}-${TS}.log" 2>&1
  echo "=== RUN S ${ctrl} END $(date +%H:%M:%S) rc=$? ==="
  sleep 8
done
echo "SMOKE-S ALL DONE $TS"
