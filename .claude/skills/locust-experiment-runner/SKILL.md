---
name: locust-experiment-runner
description: Reference for launching RAS-real Locust experiments correctly — docker setup, locust invocation, log paths, common failure recovery. TRIGGER when discussing how to actually run an experiment from a config or shell.
---

# Locust Experiment Runner — Reference

## Prerequisites
1. **Docker function container** must be running:
   ```bash
   docker run --name <NAME> -p 8080:8080 \
     systemautoscaler/sebs-dynamic_html:0.0.1 \
     uwsgi --http 0.0.0.0:8080 --master -p <CORES> -w web_server_dynamic_html:app
   ```
2. **Container ID** must be added to the experiment config under the appropriate key (check `base_experiment.py`).
3. **CPU quota** is controlled via `docker update --cpus=<N> <ID>` — the controller drives this.

## Standard launch (single experiment)
```bash
# Config-driven via base_experiment.py / locust
locust -f base_experiment.py \
  --host=http://localhost:8080 \
  --headless \
  --users <N> \
  --spawn-rate <R> \
  --run-time <SECONDS> \
  --logfile experiments/<exp-id>/locust.log \
  -- <config-path>
```
*(Adjust the trailing `-- <config-path>` based on how `base_experiment.py` accepts the config — check the file.)*

## Standard launch (multi-experiment / sweep)
Use the existing `aws-multi-runner.sh`:
```bash
./aws-multi-runner.sh
```
Inspect this script before running — it may have hardcoded paths.

## Verifying a run
- **Log files**: `./logs/<controller-name>-<timestamp>.log` and `./logs/gpppo-gp-<timestamp>.log` (for GPPPO)
- **CPU quota**: `docker inspect --format='{{json .HostConfig.CpuQuota}} {{json .HostConfig.CpuPeriod}}' <CONTAINER_ID>`
- **Container health**: `docker logs <CONTAINER_ID> --tail 50`

## Common failure modes
| Symptom | Diagnosis | Recovery |
|---------|-----------|----------|
| Locust workers exit immediately | request_maker import failure | check `request_maker.py` for syntax |
| RT always 0 in monitoring | container not warm / wrong port | hit `curl http://localhost:8080` manually |
| Cores never change | controller not wired to monitoring | verify `setMonitoring`, `setGenerator` in `setup()` |
| GP log never appears | GPPPO buffer never reached `gp_min_samples` | run longer or lower threshold |
| `mp.Process` zombie | training crashed silently | check stderr; consider `mp.set_start_method("spawn")` |

## Smoke test pattern (mandatory before long runs)
A 60s run with the same config but `--run-time 60`:
- Confirms container is reachable
- Confirms controller boots without exception
- Confirms monitoring returns finite values

If smoke test fails, do NOT escalate to full run.

## Cloud/VM specifics
- Disk space for logs can fill fast (controller logs every tick) — rotate or `tail -F` to monitor.
- Locust + torch + sklearn + GP subprocess can hit memory pressure on small VMs. Monitor with `docker stats` + `top`.
- If using AWS, `aws-runner.sh` has the canonical wrapper — read it before re-inventing.
