---
description: Full research-grade planning pipeline — Triage → Multi-Expert Panel → Codex Cross-Review. Produces a TDD-ready plan with acceptance tests.
argument-hint: <research goal — e.g. "stress test GPPPO under continuous concept drift">
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch, Agent
model: opus
---

# /plan — Research-grade pipeline for RAS-real

Goal received from user: **$ARGUMENTS**

Produce a plan that is:
- Grounded in the **current** code (not stale memory)
- Informed by recent **literature** (Scholar/arXiv)
- Cross-examined by **5 domain experts** with isolated context windows
- Refined by **Codex** as an independent second opinion
- **TDD-ready**: every actionable step ships with a pytest acceptance test

This pipeline runs in **3 phases with checkpoints**. After each phase, summarise to the user and ask for OK before proceeding (unless they tell you to run all the way through).

---

## Phase 1 — TRIAGE (parallel agents, ~3-5 min)

Create the working directory:
```bash
mkdir -p .claude/tmp/plan-$(date +%Y%m%d-%H%M%S)
```
Save its path as `$PLAN_DIR` (use a real timestamp, embed in subsequent file paths).

Launch in parallel (single message, two `Agent` tool calls):
1. **`codebase-cartographer`** with prompt:
   > Given the goal "$ARGUMENTS", produce a current snapshot of the relevant code area. Map entry points, controllers involved, state, dependencies, invariants. Output as markdown ready to paste into a plan. Save to `$PLAN_DIR/triage-codebase.md`.
2. **`academic-scholar-researcher`** with prompt:
   > Given the goal "$ARGUMENTS", scan Scholar/arXiv for related work from 2022 onwards on: safe RL shielding, GP-based safety, RL under non-stationarity, cloud autoscaling with RL, hybrid RL+control. Surface top hits, gaps, and threats to novelty. Save to `$PLAN_DIR/triage-literature.md`.

When both return:
- Stitch the two outputs into `$PLAN_DIR/triage-report.md` (just concat with section headers).
- **Print a 10-line summary** to the user.
- **Checkpoint**: ask "Procedo con la Fase 2 (Expert Panel)? sì/no/modifica"

---

## Phase 2 — EXPERT PANEL (parallel agents, ~5-8 min)

Once approved, launch **5 experts in parallel** (single message, 5 `Agent` tool calls). Each receives the SAME briefing:

> Goal: $ARGUMENTS
>
> Context: read `$PLAN_DIR/triage-report.md` first.
>
> From your specialist lens, produce:
> 1. The 3 most critical issues you see (with file:line)
> 2. 3 actionable recommendations, each with hypothesis + diff sketch + **pytest acceptance test**
> 3. Citations if you make non-trivial claims
>
> Save to `$PLAN_DIR/panel-<your-agent-name>.md`. Be concrete and brief — prose-bloat will be cut.

Experts:
1. `rl-expert`
2. `control-theory-expert`
3. `stochastic-process-expert`
4. `ai-guardrails-expert`
5. `experiment-design-expert`

When all 5 return:
- Synthesize into `$PLAN_DIR/panel-synthesis.md` with sections:
  - **Convergent recommendations** (≥3 experts agree)
  - **Divergent / contested** (experts disagree — flag explicitly)
  - **Unique insights** (only one expert raised it but it's important)
  - **Consolidated test list** (deduped acceptance tests, ready for `/tdd-cycle`)
- Print a 15-line summary.
- **Checkpoint**: ask "Procedo con la Fase 3 (Codex cross-review)? sì/no/modifica"

---

## Phase 3 — CODEX CROSS-REVIEW (~2-4 min)

Build the draft plan first:
- Concatenate triage + panel synthesis into `$PLAN_DIR/plan-draft.md`
- Add a "Proposed execution order" section (based on convergent recommendations + dependencies)

Then invoke Codex with isolated context (Codex sees ONLY the plan, not the repo):
```bash
cat "$PLAN_DIR/plan-draft.md" | codex exec - > "$PLAN_DIR/codex-review.md" 2>&1 <<'CODEX_PROMPT'
You are an independent reviewer. The user is preparing a research-grade plan
for a paper on RL guardrails for cloud autoscaling. Critique the attached plan
along these axes:

1. UNVERIFIED ASSUMPTIONS — what does the plan assume that isn't justified?
2. MISSING STEPS — what should be done but isn't in the plan?
3. WEAK ACCEPTANCE TESTS — which proposed tests would pass without proving the
   actual claim?
4. METHODOLOGICAL RISKS for a systems/ML paper — confounds, fairness, n of seeds.
5. DEPENDENCY ORDER — is the proposed execution order safe?

Be brutally specific. Reference plan section numbers. Do NOT rewrite the plan;
just critique it. Output as markdown with sections matching the 5 axes above.

The plan follows below.
CODEX_PROMPT
```
*(Note: pipe input via heredoc-style; if `codex exec -` reads stdin once, use either the prompt arg OR stdin — confirm the working invocation against the user's installed codex version. Fallback: `codex exec "<prompt>" < plan-draft.md`. If both fail, save the prompt+plan to a file and run `codex exec --skip-git-repo-check < combined.md`.)*

Build the final plan `$PLAN_DIR/plan-final.md`:
- Original draft sections
- New section **"Codex objections"** with each objection + status:
  - `addressed` (with how)
  - `deferred` (with why)
  - `disputed` (with rationale)

Print a final 20-line summary to the user with:
- File path of the final plan
- The N actionable steps with their TDD test names
- The recommended first step to attack via `/tdd-cycle`

---

## Failure handling
- If any agent crashes or returns empty: continue with the others, note the gap in the synthesis.
- If `codex exec` is unavailable or errors: save the failure reason to `$PLAN_DIR/codex-review.md` and proceed without Phase 3 — flag this clearly to the user.
- Never proceed past a checkpoint without explicit user OK.

## Hard rules
- Always create `$PLAN_DIR` first; everything goes there (it's gitignored).
- Always read fresh code in Phase 1 — never trust stale memory entries about file:line.
- Each acceptance test must be runnable as `pytest tests/.../test_x.py::test_y`.
- Do NOT implement anything in /plan — that's the next step (`/tdd-cycle`).
