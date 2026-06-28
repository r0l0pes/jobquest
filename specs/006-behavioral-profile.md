# P6: Behavioral Profile Layer — Personality-Driven Application Tone

**Status:** Spec
**Date:** 2026-06-04
**Source:** ai-job-search `02-behavioral-profile.md` — Behavioral assessment integration

---

## What

Add a structured behavioral profile that informs writing tone, Q&A answers,
and cover letter voice. The profile captures how the candidate works, their
strengths, growth areas, and communication style — and the pipeline uses it
to ensure application materials match the candidate's natural register.

## Why

JobQuest's voice enforcement (`rodrigo-voice-lite.md`) covers writing rules
(no em dashes, active voice, banned words) but not behavioral tone. Without
behavioral grounding:

- Q&A answers may sound generically confident rather than genuinely Rodrigo
- Cover letter tone may clash with how he actually communicates
- Fit evaluation (spec 001) lacks the behavioral dimension

ai-job-search treats the behavioral profile as a first-class input. The
reviewer agent specifically checks whether the cover letter's voice matches
the candidate's natural register — e.g., a collaborator shouldn't get a
combative, solo-hero tone; a persuader shouldn't get over-hedged phrasing.

## How

### Profile Structure (`prompts/behavioral_profile.md`)

```markdown
# Behavioral Profile

## Overview
Rodrigo's working style is [summary in 1-2 lines].

## Core Drives
| Drive | Level | What it means |
|---|---|---|
| [Drive 1] | High/Med/Low | [Description] |
| [Drive 2] | High/Med/Low | [Description] |

## Communication Style
- [How he writes, presents, collaborates]
- [Tone in written communication — casual/formal, direct/diplomatic]

## Strengths (in application context)
- [Strength 1]: [how to demonstrate in cover letter]
- [Strength 2]: [how to demonstrate in Q&A answers]

## Growth Areas (frame positively)
- [Area 1]: [how to acknowledge without apologizing]
- [Area 2]: [positive framing]

## Thrives In
- [Environment 1]
- [Environment 2]

## Maps to Job Posting Language
When a JD mentions these → strong behavioral fit:
- [Keyword/phrase that matches his style]

When a JD mentions these → potential friction (not deal-breaker):
- [Keyword/phrase that may clash]
```

### Integration Points

**Fit evaluation (spec 001):** The Behavioral/Culture Fit dimension reads
this profile to score alignment with the JD's implicit culture signals.

**Q&A generation (step 8):** The profile is injected into the Q&A prompt
so answers reflect Rodrigo's actual communication style — e.g., direct but
warm, confident without arrogance.

**Cover letter (step 10):** The voice rules include behavioral grounding:
"Write as someone who [communication style]. Don't use [clash pattern]."

**Reviewer (spec 005):** The reviewer checks: "Does the cover letter voice
match the candidate's behavioral profile?" — flagging mismatches.

### Profile Source

The profile can be created from:
1. Self-assessment (Rodrigo fills in the template)
2. Inference from existing cover letters and Q&A answers
3. A formal assessment (PI, DISC, StrengthsFinder) if available

For initial implementation, Rodrigo fills in a simplified version.

## Changes

| File | Change |
|---|---|
| `prompts/behavioral_profile.md` | **Create** — structured behavioral profile |
| `prompts/fit_evaluation.md` | Reference behavioral profile for Culture dimension |
| `prompts/qa_generator.md` | Inject behavioral tone instructions |
| `prompts/reviewer.md` | Add behavioral voice check to reviewer criteria |
| `modules/pipeline.py` | Load behavioral profile in `_load_voice_prefix()` |

## Implementation Plan

1. Create `prompts/behavioral_profile.md` with Rodrigo's input
2. Add behavioral loading to `_load_voice_prefix()` in `modules/pipeline.py`
3. Add behavioral tone instructions to `prompts/qa_generator.md`
4. Add behavioral check to `prompts/reviewer.md` (when implemented)
5. Dry-run and compare Q&A tone with vs. without profile

## Test Scenarios

| Category | Scenario |
|---|---|
| Happy path | Q&A answers match behavioral profile tone |
| Happy path | Cover letter voice consistent with communication style |
| Happy path | Fit evaluation uses behavioral dimension |
| Edge case | No profile exists → behavioral dimension defaults to neutral (50) |
| Edge case | Profile loaded but DD doesn't mention culture → dimension passes |
