# P4: Interview Prep Integration — Pipeline Output for Post-Application

**Status:** Spec
**Date:** 2026-06-04
**Source:** ai-job-search `/apply` workflow — Interview Preparation step

---

## What

Wire the existing interview preparation mode (`modes/prep_interview.md`) into
the pipeline as an automatic output step. After Q&A generation (step 8),
generate a structured interview prep document with STAR examples, likely
questions, and company-specific talking points.

## Why

JobQuest already has:
- `modes/prep_interview.md` — an agent mode for interview prep
- `interview-prep/story-bank.md` — STAR story bank
- Company research context from step 8 (Q&A generation uses company research)

But these are disconnected — the user must manually invoke the prep mode
after running the pipeline. Wiring them together means:

- Interview prep is ready the moment the application is submitted
- STAR examples are pre-selected based on the JD requirements
- Questions are company-specific, not generic
- No extra LLM calls (reuses step 8 context)

ai-job-search generates interview prep as a natural output of the `/apply`
workflow, not a separate mode.

## How

### Output Structure

Generate `interview_prep_<Company>.md` in the output directory:

```markdown
# Interview Preparation: [Role] at [Company]

## Company Context
[From step 8 research: mission, recent news, team structure, culture]

## Likely Questions

### Technical / Role-Specific
1. [Question derived from JD requirement 1]
   - **Talking points:** [specific experience to mention]
   - **STAR:** [reference to story bank]

2. [Question derived from JD requirement 2]
   ...

### Behavioral
1. "Tell me about a time you..."
   - **STAR:** [matched from story bank]

### Company-Specific
1. "Why [Company]?"
   - **Talking points:** [from company research + cover letter]

## Questions to Ask Them
### About the Role
- "What does success look like in the first 6 months?"
- [Role-specific questions derived from JD gaps]

### About the Team
- "How does the team divide work?"
- [Team-specific from company research]

### About Culture
- "What do people who thrive here have in common?"
- [Culture-specific from company research]

## STAR Examples (Pre-Selected)
### 1. [Story Title] — for "[Question Type]"
**S:** [Situation]
**T:** [Task]
**A:** [Action]
**R:** [Result]

## Follow-Up Timeline
- If no response after 2 weeks: [suggested follow-up]
```

### Implementation

**New pipeline step:** `step_generate_interview_prep()` in `modules/pipeline.py`
- Runs after step 8 (Q&A generation) — reuses company research context
- Reads `interview-prep/story-bank.md` for available STAR examples
- Uses LLM to:
  1. Match STAR examples to JD requirements
  2. Generate likely interview questions from JD
  3. Generate company-specific "questions to ask"
  4. Fill in company context from step 8 research
- Writes `interview_prep_<Company>.md` to output directory

**New prompt file:** `prompts/interview_prep.md`
- Structured prompt: match stories, generate questions, fill context
- ~60 lines

**LLM provider:** Reuses step 8's company research — minimal new tokens.
Use Gemini 3.1 Flash-Lite (cheapest) since this is not writing-quality work.

### Integration with Tracker

Add an "Interview Prep" column or button in `data/tracker.html` that opens
the prep document. Can link to the markdown file or embed it in a modal.

## Changes

| File | Change |
|---|---|
| `modules/pipeline.py` | Add `step_generate_interview_prep()` as step 8b |
| `prompts/interview_prep.md` | **Create** — structured interview prep prompt |
| `data/tracker.html` | Add link/button for interview prep document |
| `data/applications.json` | Add `interview_prep` field to schema |

## Implementation Plan

1. Write `prompts/interview_prep.md` — question generation + STAR matching prompt
2. Add `step_generate_interview_prep()` to `modules/pipeline.py`
3. Wire into pipeline after step 8
4. Save `interview_prep` path to `applications.json`
5. Add tracker link (optional — can be phase 2)

## Test Scenarios

| Category | Scenario |
|---|---|
| Happy path | Interview prep generated with company-specific questions |
| Happy path | STAR examples matched to JD requirements |
| Happy path | Questions-to-ask section includes role, team, culture questions |
| Edge case | Story bank has no matching STAR → generates generic behavioral Qs |
| Edge case | No company research available (step 8 skipped) → omits company-specific Qs |
| Integration | Output file saved to output directory alongside Q&A, resume, cover letter |
| Integration | Tracker shows interview prep file link |
