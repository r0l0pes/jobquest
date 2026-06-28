# P1: Fit Evaluation Gate — Pre-Pipeline Scoring

**Status:** Spec
**Date:** 2026-06-04
**Source:** ai-job-search `/apply` workflow — Step 1 fit evaluation

---

## What

A new pipeline step 0 that evaluates job fit BEFORE any tailoring or document
generation. Scores the job against the candidate's profile across 5 dimensions,
presents the result to the user, and requires explicit approval before proceeding.

If the job is a poor fit, the pipeline stops — no tokens wasted on tailoring.

## Why

Currently the pipeline runs all 11 steps unconditionally. The pipeline score
(fit scoring, spec 002) is computed at step 9 — after all the expensive LLM
calls are done. This means:

- Bad-fit jobs burn API credits and time on tailoring, ATS checks, Q&A, and
  cover letter compilation
- The user discovers a job is a 2/10 match only after waiting 2-3 minutes
- No explicit gate to say "this isn't worth your time"

ai-job-search mandates fit evaluation FIRST, before any document generation.
This spec ports that gate.

## How

### Scoring Dimensions (from ai-job-search `04-job-evaluation.md`)

| Dimension | Weight | Source |
|---|---|---|
| Technical Skills Match | 30% | Skills in master resume vs. JD requirements |
| Experience Match | 25% | Work history vs. role level and domain |
| Behavioral/Culture Fit | 15% | JD language vs. behavioral profile |
| Career Alignment | 30% | Role vs. career goals, energizing tasks |
| Location & Logistics | Pass/Fail | Location vs. constraints |

### Thresholds

| Score | Label | Action |
|---|---|---|
| 75+ | STRONG FIT | Proceed automatically |
| 60-74 | GOOD FIT | Proceed, note gaps |
| 45-59 | MODERATE | Warn user, ask to confirm |
| 30-44 | WEAK | Strong warning, discourage |
| <30 | POOR FIT | Stop pipeline |

If Location is FAIL, the pipeline stops regardless of score.

### Output Format

```
## Job Fit Evaluation: [Role] at [Company]

| Dimension | Score | Notes |
|---|---|---|
| Technical Skills | XX/100 | [note] |
| Experience Match | XX/100 | [note] |
| Behavioral Fit | XX/100 | [note] |
| Location | PASS/FAIL | [note] |
| Career Alignment | XX/100 | [note] |

**Overall Score: XX/100** — [Label]

### Key Strengths
- ...

### Gaps to Address
- ...

### Recommendation
[1-2 sentence recommendation]
```

### Implementation

**New prompt file:** `prompts/fit_evaluation.md`
- Structured prompt that takes JD + master resume + behavioral profile
- Returns JSON with scores, notes, strengths, gaps, recommendation
- ~50 lines, follows existing prompt conventions

**New pipeline step:** `step_evaluate_fit()` in `modules/pipeline.py`
- Runs before `step_scrape_job` or immediately after (needs JD text)
- Calls LLM with fit_evaluation prompt
- Parses JSON response
- Computes weighted score
- If < threshold, prints evaluation and stops
- If >= threshold, prints evaluation and continues

**User approval gate:**
- CLI mode: prints evaluation, asks "Proceed with tailoring? [Y/n]"
- Web UI mode: returns evaluation to Gradio output, user clicks "Proceed" or "Skip"
- `--auto-apply` flag skips the gate (for batch mode)

**LLM provider:** Uses the same free-first fallback chain as writing steps.
Since this is a single short call (~500 output tokens), Gemini 3 Flash is ideal.

### Fit evaluation data

The evaluation needs access to:
- Candidate skills and experience (from Notion master resume — already loaded in step 2)
- Behavioral profile (new file: `prompts/behavioral_profile.md` — see spec 006)
- Career goals and deal-breakers (from a new config section or env vars)

For initial implementation, career goals and deal-breakers can be hardcoded in
the prompt or read from a simple config file (`data/career_config.json`). The
behavioral profile spec (006) provides the structured profile format.

Without a behavioral profile, the Behavioral/Culture Fit dimension scores 50
(default neutral) and notes "No behavioral profile configured."

## Changes

| File | Change |
|---|---|
| `modules/pipeline.py` | Add `step_evaluate_fit()` as new step 0, wire into pipeline orchestration |
| `prompts/fit_evaluation.md` | **Create** — structured fit evaluation prompt |
| `apply.py` | Add `--auto-apply` flag, wire fit evaluation gate |
| `web_ui.py` | Add proceed/skip UI after fit evaluation result |
| `data/career_config.json` | **Create** — career goals, deal-breakers, location constraints |

## Implementation Plan

1. Write `prompts/fit_evaluation.md` — structured prompt with scoring rubric
2. Create `data/career_config.json` — career goals + constraints
3. Add `step_evaluate_fit()` to `modules/pipeline.py` — LLM call + parsing + gate
4. Wire into pipeline: call as first step, store result on `ctx`
5. Add `--auto-apply` flag to `apply.py`
6. Add proceed/skip to `web_ui.py` Gradio output

## Test Scenarios

| Category | Scenario |
|---|---|
| Happy path | Strong fit (85) → prints evaluation, proceeds automatically |
| Happy path | Good fit (68) → prints evaluation with gaps, proceeds |
| Happy path | Moderate fit (52) → warns user, user confirms → proceeds |
| Happy path | Moderate fit (52) → warns user, user declines → stops cleanly |
| Edge case | Weak fit (35) → strong warning, user can still force-proceed |
| Edge case | Location FAIL → stops regardless of score |
| Edge case | No behavioral profile → dimension scores 50, notes absence |
| Error path | LLM call fails → fallback through chain, eventual error if all fail |
| Integration | CLI `--auto-apply` skips gate for batch mode |
| Integration | Web UI shows evaluation + proceed/skip buttons |
