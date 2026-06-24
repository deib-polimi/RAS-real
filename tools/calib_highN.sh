#!/bin/bash
# μ_eff at high N (payload = 25000*(1+N)), low load to isolate service time.
set -uo pipefail
export DOCKER_HOST="unix:///Users/emilio-imt/.docker/run/docker.sock"
cd /Users/emilio-imt/git/RAS-real
pkill -f "locust --headless" 2>/dev/null; pkill -f "calibrate_mu" 2>/dev/null; sleep 2
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
TS=$(date +%Y%m%d-%H%M%S); LOG="logs/calibHighN-${TS}.log"
COMMON="--hosts http://localhost:8080 http://localhost:8081 --path / --container graph_set --quota-container graph_quota --app-sla 0.25 --wait-time 1 --duration 100 --warmup 20 --users 12 --cores 7"
echo "CALIB-highN START $TS" | tee "$LOG"
for nf in "2.0:75000" "3.0:100000"; do
  N="${nf%%:*}"; P="${nf##*:}"
  echo "=== N=$N payload=$P ===" | tee -a "$LOG"
  $PY tools/calibrate_mu.py $COMMON --payload-size "$P" 2>&1 | grep -E "^\[calibrate\] c=" | tee -a "$LOG"
done
echo "CALIB-highN DONE"; echo "LOGFILE=$LOG"
