#!/bin/bash
set -uo pipefail
export DOCKER_HOST="unix:///Users/emilio-imt/.docker/run/docker.sock"
cd /Users/emilio-imt/git/RAS-real
pkill -f "locust --headless" 2>/dev/null; sleep 2
TS=$(date +%Y%m%d-%H%M%S)
echo "S15-PPO START $TS"
.venv/bin/locust --headless -f locustfiles/exp-local-smoke-S15-ppo.py > "logs/smokeS15-ppo-${TS}.log" 2>&1
echo "S15-PPO DONE rc=$?"
