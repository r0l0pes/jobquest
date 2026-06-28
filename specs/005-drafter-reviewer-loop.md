# P5: Drafter-Reviewer Agent Loop — Adversarial Quality Review

**Status:** Spec
**Date:** 2026-06-04
**Source:** ai-job-search `/apply` Steps 3-4 — Reviewer Agent + Revision

---

## What

Add a reviewer agent step after the initial resume and cover letter drafts.
A separate LLM call researches the company, critiques the drafts for content
quality, and produces structured feedback. The drafter then applies revisions
before final output.

## Why

JobQuest's current 3-stage pipeline (analysis → LaTeX → compliance) uses the
same LLM for all steps. There's no adversarial review — no second pair of eyes
checking for:

- **Fabricated content:** LLM invents skills or achievements that don't exist
- **Missed keywords:** JD requirements that the drafter overlooked
- **Tone mismatches:** Cover letter voice doesn't match candidate's actual style
- **Company-specific angles:** Generic content that doesn't reflect company research
- **Repetition:** Cover letter just rephrases resume bullets

The compliance check (step 3c) only verifies that the LaTeX follows the
tailoring brief — it doesn't critique content quality or factual accuracy.

ai-job-search's reviewer agent catches these issues. A second LLM call with a
different prompt (and potentially a different model) provides an adversarial
perspective that single-pass generation cannot match.

## How

### Workflow

```
Step 3b: Draft CV + Cover Letter
    │
    ▼
Step 3c: REVIEWER — Research & Critique
    │  - Research company (WebFetch/WebSearch)
    │  - Read candidate profile + behavioral profile
    │  - Critique CV and cover letter drafts
    │  - Produce structured feedback (JSON edits + narrative suggestions)
    │
    ▼
Step 3d: DRAFTER — Revise Based on Feedback
    │  - Apply structured JSON edits
    │  - Address narrative suggestions
    │  - Do NOT fabricate content to fill gaps
    │
    ▼
Step 4: Write .tex file (existing)
```

### Reviewer Prompt (`prompts/reviewer.md`)

The reviewer prompt should produce feedback in two parts:

**Part A — Structured Edits (JSON)**
```json
[
  {
    "file": "cv_main_<company>.tex",
    "old_string": "<exact text from draft>",
    "new_string": "<replacement text>",
    "reason": "<one-line: keyword match / company angle / reframing / style>"
  }
]
```
Only for mechanical replacements where old_string is exact. Include enough
context to make it unique.

**Part B — Narrative Suggestions**
- **Missed keywords/requirements** — what to add and where
- **Company/department-specific angles** — connections between experience and
  company's strategic priorities
- **Action-oriented reframing** — passive or generic statements to rewrite
- **Tone and style issues** — cliches, hedging, inconsistent register

**Critical rule:** All suggestions must be grounded in actual profile data.
Never suggest fabricating skills, experience, or achievements.

### Revision Logic

The drafter (existing pipeline code) applies the reviewer's feedback:

1. Apply Part A JSON edits using Edit tool (string replacement on .tex files)
2. Address Part B narrative suggestions using judgment
3. Skip any suggestion that would fabricate content — note it as "Gap acknowledged"
4. Re-compile and re-inspect PDFs

### Reviewer LLM Provider

The reviewer should use a **different model** than the drafter for true
adversarial review. Recommendations:

- Primary: Gemini 3 Flash (500 RPD, fast, capable critique)
- Fallback: Gemini 3.1 Flash-Lite (1500 RPD)
- The reviewer needs reasoning capability more than writing quality

The reviewer prompt is longer than typical (includes full drafts inline),
so context window matters. All Gemini models have sufficient context (1M tokens).

### Token Efficiency

Passing full drafts inline to the reviewer saves re-reads:
- Drafter has drafts in memory from step 3b
- Pass them inline in the reviewer prompt
- Reviewer returns edits directly
- Drafter applies edits without re-reading files

Total additional tokens: ~3,000-4,000 input (drafts inline) + ~500-1,000 output
(feedback). This is ~20% more tokens for a substantial quality improvement.

## Changes

| File | Change |
|---|---|
| `prompts/reviewer.md` | **Create** — structured reviewer prompt with Part A/B output format |
| `modules/pipeline.py` | Add `step_review_drafts()` and `step_apply_review()` |
| `modules/llm_client.py` | Add `create_reviewer_client()` with separate model selection |

## Implementation Plan

1. Write `prompts/reviewer.md` — structured reviewer prompt
2. Add `create_reviewer_client()` to `modules/llm_client.py`
3. Add `step_review_drafts()` to `modules/pipeline.py` — company research + critique
4. Add `step_apply_review()` — parse JSON edits + narrative suggestions, apply to .tex
5. Wire into pipeline between steps 3b and 4
6. Add `--skip-reviewer` flag for speed mode

## Test Scenarios

| Category | Scenario |
|---|---|
| Happy path | Reviewer catches missed keyword, JSON edit applied successfully |
| Happy path | Reviewer suggests company-specific angle, drafter weaves it in |
| Happy path | Reviewer flags fabricated content → drafter skips, logs gap |
| Edge case | Reviewer returns no Part A edits (all narrative) → drafter applies Part B only |
| Edge case | Reviewer old_string doesn't match (drafter context shifted) → skip that edit, log |
| Edge case | `--skip-reviewer` flag → reviewer step skipped entirely |
| Error path | Reviewer LLM call fails → fallback through chain, pipeline continues without review |
| Integration | Revised output passes compliance check with fewer issues |
| Integration | Token count increases by ~20% for reviewer + revision pass |
