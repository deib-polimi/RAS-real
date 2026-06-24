---
description: Generate a paper-ready figure (LaTeX/PGF or matplotlib) from one or more experiment runs.
argument-hint: <topic — e.g. "p95 latency over time PPO vs GPPPO under drift">
allowed-tools: Read, Write, Bash, Grep, Glob
model: sonnet
---

# /paper-figure — Paper-ready figure generation

Topic: **$ARGUMENTS**

## Steps
1. Identify the runs needed for the figure (ask the user if ambiguous).
2. Use `metrics-analyzer` (read its output if recent, or invoke it) to produce the underlying numbers.
3. Generate either:
   - **PGF/TikZ** (preferred for the paper — vector, embeds cleanly in LaTeX) saved to `paper/figures/<slug>.tex`
   - **matplotlib PDF** if PGF is overkill, saved to `paper/figures/<slug>.pdf`
4. Generate a short caption draft and a `\input{}` snippet to paste into the paper.
5. If `paper/` doesn't exist yet, create it and add a `paper/figures/` subdir.

## Style conventions
- **Black-and-white friendly** (use markers + linestyles, not just colours)
- **Axis labels + units** (e.g. `Latency [s]`, `Time [s]`)
- **Legend in plot or below** — depends on figure type
- **Font size** ≥ 8pt at final paper width
- Show **median + IQR** for multi-seed data, not mean ± std

## Output to user
- Path of the .tex / .pdf
- Caption draft (3-4 sentences)
- LaTeX snippet to include
- Any data caveats (single seed, partial run, etc.)

## Hard rules
- Never invent numbers — always derive from `metrics-analyzer` output.
- If multi-seed data isn't available, say so explicitly in the caption ("single seed, illustrative").
- Match figure style to existing paper figures if any (`*.tex` files in the repo root look like PGF — match that style).
