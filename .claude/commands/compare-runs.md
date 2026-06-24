---
description: Compare metrics between two RAS-real experiment runs (e.g. PPO vs GPPPO baseline).
argument-hint: <run-A-id-or-dir> <run-B-id-or-dir>
allowed-tools: Read, Bash, Grep, Glob, Agent
model: sonnet
---

# /compare-runs — Diff metrics across two runs

Targets: **$ARGUMENTS**

Resolve each argument to an experiment directory under `experiments/exp-*` (accept either full path or just the exp-id suffix).

Delegate to `metrics-analyzer` with:
> Compare run A=<path-A> vs B=<path-B>. Compute the standard metric set
> (sla_violation_rate, lat_p95/p99, cost, time_to_recovery, controller_chatter,
> compensation_share, gp_active_share). Produce a paired comparison table
> with relative deltas. Highlight any |Δ| > 10%. Report time-series highlights
> for any divergence.

After the agent returns:
- Print the comparison table.
- If any metric regresses by >10% from A to B, flag it loudly with a red-flag emoji.
- Suggest follow-up: `/expert-panel` if results are surprising, `/paper-figure` if they're publication-ready.

## Hard rules
- Always do a paired comparison if both runs used the same workload trace.
- If the workloads differ, say so in the report and downgrade conclusions.
- Never average across runs that used different SLAs or controller configs without flagging it.
