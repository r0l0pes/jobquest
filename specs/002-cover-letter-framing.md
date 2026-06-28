# P2: Cover Letter Framing Upgrade — Forward-Looking Task-Solving Structure

**Status:** Spec
**Date:** 2026-06-04
**Source:** ai-job-search `03-writing-style.md` — Forward-Looking Framing

---

## What

Upgrade the cover letter prompt and template to use **forward-looking
task-solving framing** instead of retrospective CV repetition. The cover
letter should focus on what the candidate can solve for the employer, not
just recount what they've done.

## Why

ai-job-search's cover letter philosophy is fundamentally different from
JobQuest's current approach:

| Aspect | Current (JobQuest) | Target (ai-job-search) |
|---|---|---|
| Focus | Past achievements | Tasks the candidate can solve |
| Structure | CV-like chronology | Motivation → task-solving → evidence |
| Company paragraph | Late or absent | Early, specific to this company |
| Tone | "Here's what I did" | "Here's how I'll help you" |
| Bullets | Outcome-focused | Method + outcome + relevance |

JobQuest generates cover letters but they read as a prose version of the
resume. This makes them weaker than they could be — and weaker than the
resume they accompany.

## How

### Cover Letter Structure (from ai-job-search)

**1. Opening paragraph (2-3 sentences)**
- State the role and why you're writing
- Immediately connect background to the role
- Make it specific to THIS company/role — not template

**2. Motivation / Why this company (placed early)**
- Explain why THIS company specifically
- Reference their mission, products, market position
- Focus on how you'll contribute to their goals
- If you spoke with someone, reference the conversation

**3. Body — Task-solving focus**
- Lead with "which of their tasks you can solve and how"
- Describe methods, tools, knowledge you'll bring
- Use 1-2 brief past examples ONLY to back up forward-looking claims
- 3-5 bullets, each: specific, outcome-oriented, shows initiative

**4. Closing**
- Brief, confident, forward-looking
- "I look forward to hearing from you" or equivalent

### Prompt Changes

**`prompts/qa_generator.md`** — the cover letter section currently
generates the letter body. Add these rules:

```
## Cover Letter Framing

The cover letter is NOT a CV repetition. Frame everything forward:
- Lead with tasks you can solve for THIS employer, not what you've done before
- Describe your approach: methods, tools, knowledge
- Use past examples only as brief evidence for forward-looking claims
- The motivation paragraph goes first after the opening
- Reference the company's specific mission, products, or market position
- Maximum 3-5 outcome-oriented bullets
```

**`templates/cover_letter.tex`** — add a `\companymotivation` section
between the opening and the body, or restructure the existing sections:

```latex
% After the greeting
\opening{[Greeting]}

% Why this company specifically (NEW)
\companyparagraph{[2-3 sentences on why this specific company]}

% Body with task-solving focus
\begin{letterbody}
  [Forward-looking paragraphs describing what you'll solve]
\end{letterbody}
```

### Writing Style Rules (add to `rodrigo-voice-lite.md`)

- Demonstrate, don't state: "I built X" not "I am skilled at X"
- No cliches: "passionate about", "hit the ground running", "leverage my skills"
- No apologetic language: "I think I could" → "I bring X, demonstrated by Y"
- Interview backtrack test: could you explain this in an interview without saying
  "well, what I actually meant was..."?

## Changes

| File | Change |
|---|---|
| `prompts/qa_generator.md` | Add forward-looking framing rules to cover letter section |
| `templates/cover_letter.tex` | Add `\companyparagraph` section, restructure body |
| `prompts/rodrigo-voice-lite.md` | Add demonstrate-don't-state, no-cliches, no-apologies rules |
| `modules/pipeline.py` | Update `step_compile_cover_letter` to handle new template sections |

## Implementation Plan

1. Update `prompts/rodrigo-voice-lite.md` — add writing style rules
2. Update `prompts/qa_generator.md` — add cover letter framing instructions
3. Update `templates/cover_letter.tex` — add company motivation section
4. Update `modules/pipeline.py` — handle new template placeholders
5. Dry-run on existing job → compare old vs new cover letter quality

## Test Scenarios

| Category | Scenario |
|---|---|
| Happy path | Cover letter generated with company-specific motivation paragraph |
| Happy path | Cover letter leads with task-solving, not CV recap |
| Happy path | Past examples used as evidence only, not as primary content |
| Edge case | Template handles missing company research (generic placeholder) |
| Edge case | German cover letter applies same framing rules |
| Integration | Cover letter + resume don't duplicate content |
