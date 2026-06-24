#!/bin/bash
set -uo pipefail
export DOCKER_HOST="unix:///Users/emilio-imt/.docker/run/docker.sock"
cd /Users/emilio-imt/git/RAS-real
pkill -f "locust --headless" 2>/dev/null; sleep 2
TS=$(date +%Y%m%d-%H%M%S)
for scen in BR50 FC; do
  echo "=== PROBE ${scen} (PPO) start $(date +%H:%M:%S) ==="
  .venv/bin/locust --headless -f locustfiles/exp-local-smoke-${scen}-ppo.py > "logs/probe-${scen}-ppo-${TS}.log" 2>&1
  echo "=== PROBE ${scen} END rc=$? ==="
  sleep 8
done
echo "PROBES DONE $TS"
