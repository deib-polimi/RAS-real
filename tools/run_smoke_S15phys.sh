#!/bin/bash
set -uo pipefail
export DOCKER_HOST="unix:///Users/emilio-imt/.docker/run/docker.sock"
cd /Users/emilio-imt/git/RAS-real
pkill -f "locust --headless" 2>/dev/null; sleep 2
TS=$(date +%Y%m%d-%H%M%S)
for ctrl in mmcpi handover; do
  echo "=== S15 ${ctrl} start $(date +%H:%M:%S) ==="
  .venv/bin/locust --headless -f locustfiles/exp-local-smoke-S15-${ctrl}.py > "logs/smokeS15-${ctrl}-${TS}.log" 2>&1
  echo "=== S15 ${ctrl} END rc=$? ==="
  sleep 8
done
echo "S15-PHYS DONE"
