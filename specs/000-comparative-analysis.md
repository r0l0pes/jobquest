# 000: Comparative Analysis — What JobQuest Can Take from ai-job-search

**Status:** Reference
**Date:** 2026-06-04
**Source:** https://github.com/MadsLorentzen/ai-job-search

---

## Context

Both projects solve the same core problem — automated job application
pipelines — but with different architectural philosophies:

| | JobQuest (r0l0pes) | ai-job-search (MadsLorentzen) |
|---|---|---|
| **Runtime** | Python 3.14 + Gradio 6 web UI | Claude Code slash-command framework |
| **Entry point** | `JobQuest.command` → 3 browser tabs | `claude` CLI → `/setup` / `/scrape` / `/apply` |
| **Pipeline** | 11 steps, multi-provider LLM free-first fallback | Drafter-reviewer agent pattern, single-provider |
| **Output** | Tailored PDF resume + ATS report + Q&A + cover letter | Tailored LaTeX CV + cover letter + interview prep |
| **Discovery** | Exa API, 12+ remote boards, live streaming log | Danish job portals (Jobindex, Jobnet, etc.), CLI tools |
| **Tracking** | Sortable HTML tracker with editable modals | CSV-based tracker |
| **Profiling** | 3 Notion-backed resume variants, `rodrigo-voice-lite.md` | 7 structured profile files (candidate, behavioral, writing, evaluation, CV, cover letter, interview) |

This document captures the gap analysis between the two projects and the
prioritized features being ported to JobQuest.

---

## What JobQuest Does Better (Preserve)

| Capability | Why it's stronger |
|---|---|
| **Multi-provider LLM fallback** | Gemini → Groq → SambaNova → OpenRouter → OpenCode Go chain. ai-job-search uses a single provider. |
| **ATS keyword coverage scoring** | Automated 60-80% target range check with cross-provider fallback. ai-job-search has no ATS analysis. |
| **3-stage resume tailoring** | Analysis brief → LaTeX generation → compliance check. ai-job-search is single-pass drafter. |
| **Notion integration** | Master resume read/write, application tracking. ai-job-search uses local markdown files. |
| **Web UI** | Gradio browser UI with 3 parallel slots, per-item language toggles. ai-job-search is CLI-only. |
| **Tracker editing** | Inline editable Q&A, cover letter, resume with recompile PDF. ai-job-search has CSV. |
| **German language support** | Per-item EN/DE toggles, Du-detection, T1 fontenc, German anti-pattern injection. |
| **Job discovery breadth** | Exa API with 12+ remote-only boards, live streaming log, cancel/discover. ai-job-search has 4 Danish portals. |

---

## Gap Analysis — What ai-job-search Has That JobQuest Doesn't

### 1. Drafter-Reviewer Agent Pattern (highest value)

ai-job-search's `/apply` runs a two-agent workflow: one agent drafts, a
separate reviewer agent researches the company and critiques the drafts.
The reviewer produces structured JSON edits + narrative suggestions, and
the drafter revises before final output.

JobQuest's step 3c is a compliance check (brief vs. LaTeX) — it verifies
the LLM followed its own plan, not that the output is genuinely good for
this specific company. An adversarial critique loop directly improves
output quality by catching fabrications, missed keywords, and tone mismatches.

→ **Spec:** [005-drafter-reviewer-loop](005-drafter-reviewer-loop.md)

### 2. Fit Evaluation Before Proceeding

ai-job-search mandates evaluating fit FIRST — scoring across 5 dimensions
(Skills, Experience, Behavioral, Location, Career Alignment) — and
presenting the result before any document generation. If a job is a poor
fit, no tokens are wasted.

JobQuest's fit score is computed at step 9 — after all the expensive
LLM calls. This is a design flaw: bad-fit jobs burn credits and time
unnecessarily.

→ **Spec:** [001-fit-evaluation-gate](001-fit-evaluation-gate.md)

### 3. Behavioral Profile Layer

ai-job-search separates candidate data into 7 structured files, including
a behavioral profile (PI/DISC/self-assessment) that drives cover letter
tone, Q&A voice, and fit evaluation.

JobQuest collapses this into `rodrigo-voice-lite.md` (writing rules only).
The behavioral layer directly improves Q&A answers and cover letter authenticity.

→ **Spec:** [006-behavioral-profile](006-behavioral-profile.md)

### 4. Forward-Looking Cover Letter Framing

ai-job-search's cover letters focus on "tasks you can solve for the employer"
rather than recounting achievements. The motivation paragraph comes early;
company-specific research is woven throughout. This is a prompt-level change
with no new infrastructure.

→ **Spec:** [002-cover-letter-framing](002-cover-letter-framing.md)

### 5. PDF Compile-and-Inspect Loop

ai-job-search mandates visual PDF inspection after every compile: exactly
2 pages for CV, no orphaned entry titles, exactly 1 page for cover letter,
bullet font matching body font. LaTeX exit code 0 is not enough — silent
layout bugs are common and only caught by visual inspection.

→ **Spec:** [003-pdf-compile-inspect](003-pdf-compile-inspect.md)

### 6. Interview Prep Output

ai-job-search generates interview prep (STAR examples, likely questions,
company-specific talking points) as a natural output of the apply workflow.
JobQuest has `modes/prep_interview.md` and `interview-prep/story-bank.md`
but they're disconnected from the pipeline.

→ **Spec:** [004-interview-prep-integration](004-interview-prep-integration.md)

### 7. Salary Benchmarking

ai-job-search includes `salary_lookup.py` — fuzzy company name matching
with city filtering and structured JSON output. BYO-data design: if no
salary data exists, the step is silently skipped. Provides concrete data
for salary expectation questions in Q&A.

→ **Spec:** [007-salary-benchmarking](007-salary-benchmarking.md)

### 8. /upskill — Skill Gap Analysis

ai-job-search analyzes tracked job postings against the candidate profile
to identify skill gaps, build a priority-graded heatmap, and generate a
learning plan with web-searched resources and dependency-ordered study
sequence. Turns the application tracker into a career development tool.

→ **Spec:** [008-upskill-gap-analysis](008-upskill-gap-analysis.md)

---

## Prioritization Framework

**Method:** ICE (Impact × Confidence × Ease) / 3

ICE was chosen over RICE because:
- No hard reach data (single-user tool, no user base to measure)
- Qualitative confidence in feature value (proven in ai-job-search)
- Speed matters (Rodrigo is actively job hunting, needs improvements this week)

### Scoring Rubric

| Score | Impact | Confidence | Ease |
|---|---|---|---|
| 9-10 | Dramatically improves application success | Already shipped in equivalent system | Prompt-only change, zero new infrastructure |
| 7-8 | Significant quality improvement | Strong pattern from reference, low adaptation risk | New pipeline step, one new file |
| 5-6 | Noticeable improvement | Conceptually sound but unvalidated in this context | Multiple new files, new integration points |
| 3-4 | Nice-to-have, low urgency | Speculative benefit | New command/tool, external dependencies |
| 1-2 | Cosmetic or very long-term | High uncertainty | Major new subsystem |

### Prioritization Matrix

| # | Feature | Impact | Confidence | Ease | ICE | Bucket | Rationale |
|---|---|---|---|---|---|---|---|
| 1 | Fit evaluation gate | 8 | 9 | 9 | **8.7** | Must | Prevents wasted runs. One prompt + gate check. |
| 2 | Cover letter framing | 7 | 9 | 9 | **8.3** | Must | Prompt-only. Immediate quality boost. |
| 3 | PDF compile-inspect | 6 | 9 | 7 | **7.3** | Should | Prevents layout bugs. New retry logic. |
| 4 | Interview prep integration | 5 | 9 | 8 | **7.3** | Should | Reuses existing `prep_interview.md`. Low effort. |
| 5 | Drafter-reviewer loop | 9 | 7 | 4 | **6.7** | Should | Highest quality impact. New LLM call + prompts. |
| 6 | Behavioral profile | 5 | 6 | 8 | **6.3** | Could | Improves Q&A/cover tone. Depends on profile creation. |
| 7 | Salary benchmarking | 3 | 8 | 7 | **6.0** | Could | Optional. Requires data population. |
| 8 | /upskill gap analysis | 4 | 7 | 3 | **4.7** | Won't | Career tool, not application tool. High effort. |

### Bucket Definitions

| Bucket | When | Definition |
|---|---|---|
| **Must** | This week | Directly prevents waste or improves output with minimal effort |
| **Should** | This week if time | High quality impact but more implementation effort |
| **Could** | Next week | Valuable but not urgent; depends on other work or data |
| **Won't** | After job search | Career planning tool; build when actively employed |

---

## Scoring Commentary

**Fit evaluation gate (ICE 8.7):** Highest ROI. A single short LLM call
(~500 tokens) can prevent 2-3 minutes of pipeline work on a bad-fit job.
Pattern is proven in ai-job-search. Zero new infrastructure — just a prompt
file and a gate check in `pipeline.py`.

**Cover letter framing (ICE 8.3):** The existing cover letters work but
read as CV prose. Forward-looking task-solving framing requires no new code
— only prompt changes to `qa_generator.md` and minor template adjustments.

**PDF compile-inspect (ICE 7.3):** LaTeX layout bugs are silent and
embarrassing. The inspection rules are concrete and implementable without
LLM (pdftotext + regex for structural checks). New retry loop adds
complexity but prevents regressions.

**Interview prep (ICE 7.3):** The content already exists (`modes/prep_interview.md`,
`story-bank.md`). Wiring it into the pipeline is a one-step addition.
Tied with PDF inspect on ICE but lower impact — PDF bugs are more visible
than missing interview prep.

**Drafter-reviewer (ICE 6.7):** Highest impact score (9) driven down by
low ease (4). A second LLM call with a different prompt, structured JSON
output format, and revision logic is the most complex change in this set.
But it's also the single biggest quality lever — no other change catches
fabrications and missed keywords as effectively.

**Behavioral profile (ICE 6.3):** Confidence is lower because the benefit
depends on how well the profile captures Rodrigo's actual communication
style. A poorly-written profile produces worse output than none.

**Salary benchmarking (ICE 6.0):** The tool ports easily (already Python)
but the value is entirely dependent on populating `salary_data.json`.
Without data, it's dead code.

**/upskill (ICE 4.7):** Genuinely useful for career planning but solves
a different problem than "get hired now." The effort is high (new CLI
command, web search integration, report generation). Right feature,
wrong moment.

---

## What Was Excluded (and Why)

| Feature | Reason for exclusion |
|---|---|
| ai-job-search's `cover.cls` + Lato/Raleway fonts | JobQuest's LaTeX template works. Font swap is cosmetic. |
| Danish job portal CLI tools | Geographically irrelevant (Rodrigo targets Germany/EU). |
| `/setup` onboarding (documents folder scan) | JobQuest already has 3 Notion resume variants + `rodrigo-voice-lite.md`. |
| `/expand` competency discovery | Requires documents folder population. Lower priority than the 8 features listed. |
| CSV-based tracker | JobQuest's JSON + HTML tracker is more feature-rich. |
| Single-provider LLM | JobQuest's multi-provider fallback is architecturally superior. |

---

## Spec Index

| Priority | Spec | ICE | Bucket |
|---|---|---|---|
| 001 | [Fit evaluation gate](001-fit-evaluation-gate.md) | 8.7 | Must |
| 002 | [Cover letter framing upgrade](002-cover-letter-framing.md) | 8.3 | Must |
| 003 | [PDF compile-and-inspect loop](003-pdf-compile-inspect.md) | 7.3 | Should |
| 004 | [Interview prep integration](004-interview-prep-integration.md) | 7.3 | Should |
| 005 | [Drafter-reviewer agent loop](005-drafter-reviewer-loop.md) | 6.7 | Should |
| 006 | [Behavioral profile layer](006-behavioral-profile.md) | 6.3 | Could |
| 007 | [Salary benchmarking hook](007-salary-benchmarking.md) | 6.0 | Could |
| 008 | [Upskill gap analysis](008-upskill-gap-analysis.md) | 4.7 | Won't |
