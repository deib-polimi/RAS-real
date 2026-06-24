---
description: Standalone Phase 2 of /plan — interrogate the 5 domain experts in parallel and synthesize.
argument-hint: <topic or question for the panel>
allowed-tools: Read, Write, Bash, Agent
model: opus
---

# /expert-panel — 5 specialist views in parallel

Topic: **$ARGUMENTS**

Use this when you want multi-perspective input on a specific question without re-running triage.

## Steps
1. Create `$PANEL_DIR=.claude/tmp/panel-$(date +%Y%m%d-%H%M%S)`.
2. If the user has a recent triage report (`.claude/tmp/triage-*` or `.claude/tmp/plan-*`), include its path in the briefing. Otherwise instruct experts to read the codebase fresh.
3. Launch in parallel (single message, 5 `Agent` calls), each with this briefing:
   > Topic: $ARGUMENTS
   >
   > Read the relevant code first. From your specialist lens, produce:
   > 1. The 3 most critical issues you see (file:line if applicable)
   > 2. 3 actionable recommendations, each with hypothesis + diff sketch + pytest acceptance test
   > 3. Citations for non-trivial claims
   >
   > Save your output to `$PANEL_DIR/<your-agent-name>.md`.
   Agents: `rl-expert`, `control-theory-expert`, `stochastic-process-expert`, `ai-guardrails-expert`, `experiment-design-expert`.
4. Synthesize into `$PANEL_DIR/synthesis.md`:
   - **Convergent**: ≥3 experts agree
   - **Divergent**: experts disagree (highlight)
   - **Unique**: single-expert insights worth keeping
   - **Test list**: dedup'd pytest acceptance tests
5. Print a 15-line summary to the user.

## Optional flag
- If `$ARGUMENTS` includes `--with-reviewer`, also launch `systems-paper-reviewer` (currently not defined — TBD; if missing, skip with a note).

## Hard rules
- Always parallel, never sequential.
- Always synthesize — do not dump 5 raw outputs on the user.
- Flag disagreements; don't silently average them.
