---
description: Red-Green-Refactor cycle for a single change. Writes failing test first, then implementation, then verifies green.
argument-hint: <change description — e.g. "fix bug A1: prev_action_ppo must be the cores delta">
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
model: opus
---

# /tdd-cycle — TDD enforcement for RAS-real

Change to make: **$ARGUMENTS**

Run a strict red-green-refactor cycle. Skip lightly only if the change has no testable invariant (logging, README, config tuning); otherwise enforce.

---

## Step 1 — RED (failing test first)

Delegate to `tdd-author`:
> Change requested: $ARGUMENTS.
>
> Read the relevant code, identify the invariant being established/restored,
> write the failing pytest test in `tests/controllers/` (or wherever fits),
> run it, confirm it fails for the right reason, then stop.
>
> Do NOT implement the fix.

Wait for `tdd-author` to return with: test path, expected failure mode, run command.

**Checkpoint with user**: print the test code (read it), explain the invariant, ask "il test cattura l'intent? sì/no/modifica".

---

## Step 2 — GREEN (minimal implementation)

Once the test is approved, implement the **minimal** change to make it pass.
- Edit only the files necessary
- No drive-by refactors
- No new abstractions
- After each Edit, re-run the test:
  ```bash
  pytest <test_path> -x -v
  ```
- Stop when the test passes.

If the test goes green but **other tests regress**, stop and treat the regression as a new RED step.

---

## Step 3 — REFACTOR (optional, only if obvious win)

If the implementation reveals a clear simplification (DRY, naming), apply it WITHOUT changing observable behaviour. Re-run the full test suite:
```bash
pytest tests/ -x
```
If everything stays green, commit the refactor as a separate logical step (don't mix with the green commit if you decide to commit later).

If no obvious simplification, skip refactor.

---

## Step 4 — Cross-review (optional but recommended for controller changes)

For changes in `controllers/`, suggest:
```
/codex-cross-review <diff-of-changed-files>
```
Don't auto-run — let the user decide.

---

## Final report
```
## TDD Cycle Complete

- Test: <path>::<name> — GREEN
- Files changed: <list>
- Lines: +<X> -<Y>
- Other tests: <N> passing, <N> total
- Refactor: applied / skipped (reason)

Suggested next:
- /codex-cross-review <files>
- git diff to review before commit
```

## Hard rules
- **Always RED first**, no exceptions for "trivial" changes that touch controller logic.
- Implementation step must be MINIMAL — if you add ≥3 files or refactor unrelated code, abort and re-plan.
- Never skip running the test after the green step "because it should work" — actually run it.
- Never commit without user approval.
