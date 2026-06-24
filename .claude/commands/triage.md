---
description: Standalone Phase 1 of /plan — codebase snapshot + literature scan, no expert panel, no codex.
argument-hint: <topic to triage>
allowed-tools: Read, Write, Bash, Grep, Glob, WebSearch, WebFetch, Agent
model: opus
---

# /triage — Snapshot of code + literature

Topic: **$ARGUMENTS**

Use this when you want a quick lay of the land without committing to the full /plan pipeline.

## Steps
1. Create `$TRIAGE_DIR=.claude/tmp/triage-$(date +%Y%m%d-%H%M%S)`.
2. Launch in parallel (single message, 2 `Agent` calls):
   - `codebase-cartographer` → save `$TRIAGE_DIR/codebase.md`
   - `academic-scholar-researcher` → save `$TRIAGE_DIR/literature.md`
3. Concat into `$TRIAGE_DIR/triage-report.md`.
4. Print a 10-line summary to the user with the file path and a "next step" suggestion (typically `/expert-panel` or `/plan`).

## Hard rules
- Run agents in parallel, not sequentially.
- Don't start work on the topic — this is reconnaissance only.
