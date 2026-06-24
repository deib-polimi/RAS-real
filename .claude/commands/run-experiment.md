---
description: Launch a RAS-real experiment from a config file with smoke test, full run, and artifact capture.
argument-hint: <path-to-config.json> [--smoke-only] [--duration=<seconds>]
allowed-tools: Read, Bash, Grep, Agent
model: sonnet
---

# /run-experiment — Orchestrated experiment launch

Config: **$ARGUMENTS**

Delegate to `experiment-runner` agent with the parsed arguments. The agent will:
1. Validate the config (call to `experiment-config-validator` skill mentally)
2. Pre-flight docker (don't auto-start container)
3. Smoke-test (if not `--smoke-only` then a short pre-run)
4. Full run via locust
5. Verify completion and capture artifacts
6. Return a structured run report

After the agent returns:
- Print the run report.
- Suggest follow-up: `/compare-runs <this> <baseline>` if a baseline exists, otherwise `/expert-panel` to discuss results.

## Hard rules
- Never auto-start the docker container — the user controls cloud cost.
- Always smoke-test before a full run unless `--smoke-only` is set.
- If the smoke test fails, abort and surface the failure mode.
