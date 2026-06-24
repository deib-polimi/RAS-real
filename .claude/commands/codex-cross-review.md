---
description: Independent cross-review of a plan, diff, or PR via the Codex CLI installed locally.
argument-hint: <path-to-file-to-review> [--mode=plan|diff|pr]
allowed-tools: Read, Write, Bash
model: sonnet
---

# /codex-cross-review — Second opinion via Codex

Target: **$ARGUMENTS**

Use Codex as an external critic. Codex has its own context and won't be biased by our conversation.

## Modes

### `--mode=plan` (default if argument is a `.md` file)
For reviewing a plan/design document.
```bash
codex exec --skip-git-repo-check < <(cat <<EOF
You are an independent reviewer. Critique the following plan along:
1. Unverified assumptions
2. Missing steps
3. Weak acceptance tests
4. Methodological risks for a systems/ML paper
5. Dependency order safety

Be brutally specific. Reference section numbers. Do NOT rewrite — critique only.

--- PLAN ---
$(cat "$TARGET_FILE")
EOF
)
```

### `--mode=diff` (default if argument is a `.diff` or `.patch` file, or a git ref)
For reviewing code changes.
```bash
codex exec review --against main
# or for a specific file/ref:
git diff $REF | codex exec --skip-git-repo-check "Review this diff for correctness, regressions, and TDD coverage."
```

### `--mode=pr <PR-number>`
For reviewing an open PR (uses `gh` if available).
```bash
gh pr diff $PR_NUMBER | codex exec --skip-git-repo-check "Review this PR..."
```

## Output handling
- Save raw Codex output to `.claude/codex-runs/<timestamp>-<mode>.md` (gitignored).
- Print a 10-line summary to the user with: number of objections raised, top 3 most severe, file path of full review.
- If the user wants to act on objections: suggest `/tdd-cycle` for each that has a clear test target.

## Hard rules
- **Never auto-apply Codex's suggestions** — always surface them for user review.
- If `codex` is not on PATH or fails, report the error verbatim and skip — don't silently substitute another tool.
- If Codex's output is empty or nonsensical, retry once with a more constrained prompt; if still bad, report and stop.
- Sandbox: pass only the target content, not the whole repo (this preserves the "independent reviewer" property).
