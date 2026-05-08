# JobQuest — Product Requirements Document

**Product:** JobQuest
**Owner:** Rodrigo Lopes
**Date:** March 2026
**Status:** Pre-build. Spec complete. Development not started.
**INTERNAL — do not commit to git, do not share publicly.**

---

## Development Approach: Spec-Driven Development

JobQuest SaaS is built through spec-driven development. Every feature, screen, and behaviour is defined in writing before any code is written. DeepSeek builds from this spec. Claude reviews all output before it ships. Rodrigo does not write SaaS code.

Rules:
- DeepSeek follows the spec. It does not make product decisions.
- Ambiguities are flagged to Claude before assuming.
- Nothing ships without Claude's review.
- Phases are completed in order. No skipping ahead.

---

## One-Line Pitch

Paste a job URL. Get a tailored PDF resume, ATS score, and application answers in under 5 minutes.

---

## The Problem

Applying for jobs requires significant manual effort per application: tailoring a resume, checking ATS keywords, writing cover letters and Q&A answers. Most people either apply with a generic resume (low success rate) or spend 2-3 hours per application (unsustainable at volume).

Existing tools solve one part of the problem. None solve all of it from a single URL.

---

## The Solution

A personal application engine. User pastes a job URL. The pipeline:
1. Scrapes the job posting automatically
2. Reads the user's profile (master resume, case studies, metrics, skills, Q&A templates)
3. Tailors the resume in two stages (analysis brief + LaTeX generation)
4. Checks ATS keyword coverage and applies edits
5. Compiles a PDF
6. Generates answers to application form questions
7. Logs the application to the tracker

Output: tailored PDF + match percentage + Q&A answers, in 2-3 minutes.

---

## Competitive Analysis

| Tool | What it does | Gap |
|---|---|---|
| Rezi | ATS scoring + AI bullet points | No auto-tailoring from URL, no Q&A |
| Teal | Resume tailoring + job tracker | Basic ATS, no Q&A, no PDF re-render |
| Jobscan | Deep ATS scoring only | Analysis only, no rewriting, no Q&A |
| Kickresume | Design + cover letter | Design-first, weak ATS, no tracking |
| Huntr | Tracker + tailoring | No ATS score, no Q&A |
| Simplify | Auto-fill application forms | No resume tailoring |
| LazyApply | Auto-apply at scale | 25-40% failure rate, generic answers |

No existing tool does all of this in one pipeline from a single URL.

### Positioning

> One URL. Two minutes. A tailored PDF, a match score, and answers to every application question.

### European market opportunity

No AI resume tool focuses on Europe. German/Spanish/French job boards (StepStone, InfoJobs, APEC) are unsupported by all competitors. Multilingual output is a v2 feature — plan for it in the data model.

---

## User Flows

### Primary flow

```
1. Land on homepage
2. Sign up (email + password)
3. Onboarding: build profile (master resume required; case studies, metrics, skills, Q&A templates optional but strongly encouraged)
4. Dashboard: paste job URL + optional application questions
5. Click Run (credits checked and deducted BEFORE pipeline starts)
6. Progress screen: live step-by-step updates with live decisions shown
7. Results: PDF download + match % + Q&A answers + before/after diff
8. Run saved to application tracker automatically
```

### Edge cases

| Scenario | Handling |
|---|---|
| Job URL requires login | Error: "This URL requires a login. Paste the job description text instead." Provide fallback text input. |
| No resume on file | Block submission: "Add your resume first" with link to profile page. |
| Pipeline fails mid-run | Show which step failed. Offer retry. Refund the credit. Never charge for failures. |
| Same URL submitted twice | Detect duplicate (hash the URL per user). Ask: "You applied here on [date]. Run again?" |
| Poor output quality | Thumbs-down on results page. Logs run ID for debugging. Does not refund automatically. |
| Job description > 5,000 words | Truncate, show notice. |
| Non-English job posting | Warn: "Non-English JD detected. Output will be in English." Full multilingual is v2. |
| Credits = 0 at submission | Block at submission. Show credits page. Never start a run without credits. |
| pdflatex fails | Show error. Refund credit. Save .tex file so user can debug or report. |
| All LLM providers rate-limited | Queue the run, retry in 2 minutes. Show "providers are busy" message. |
| Free credit abuse (multiple accounts) | Email verification required before credits activate. Block known disposable email domains. |

---

## Onboarding Philosophy — Trash In, Trash Out

The output quality of every JobQuest run is a direct function of the input quality. This is not a disclaimer. It is the central product truth and must be communicated clearly from the first screen a new user sees.

A user who pastes a thin 200-word resume and skips everything else gets a mediocre result. A user who invests 30 minutes building a rich profile gets applications that are genuinely hard to distinguish from hand-crafted ones.

This is the same principle known in data and machine learning as "garbage in, garbage out." Substance in, substance out.

### What this means for onboarding

The onboarding flow does not end at "paste your resume." It ends when the user has a complete profile. The app must:

1. Show a profile completeness indicator across all five sections
2. Explain what each section does and why it improves output
3. Give concrete examples of what good looks like
4. Never let a user think they are done when they have only a resume

### Profile completeness and output quality

| Profile state | What the pipeline can do |
|---|---|
| Master resume only | Basic tailoring. Keywords added. Summary updated. Q&A answers thin. |
| Resume + skills bank | Better match %. Skills section accurately targeted. |
| Resume + case studies | Strong Q&A answers. Behavioral questions answered with real stories. |
| Resume + metrics bank | Quantified bullets. Numbers placed where they matter. |
| Full profile | Full tailoring. Every section optimised. Q&A answers indistinguishable from hand-written. |

### Why this is the real moat

Once a user has built a rich profile, they will not switch to a competitor. The switching cost is rebuilding everything from scratch. Onboarding quality is the most important retention driver in the product.

### Profession-agnostic by design

Because the pipeline draws entirely from what the user provides, there is nothing role-specific in the product logic. A surgeon with a rich profile gets a strong surgeon application. An engineer gets a strong engineer application. JobQuest is not a "PM resume tool." It is a personal application engine that gets better the more you feed it.

### Onboarding copy tone

Frame each profile section as a multiplier, not an optional extra:

- "Case studies power your Q&A answers. Without them, answers will be generic."
- "Your metrics bank is where we get the numbers that make your bullets credible."
- "Skills bank: tell us what you know, and we make sure every application shows it."
- "Q&A templates: add questions you expect to be asked. The better the templates, the sharper the answers."

---

## Pricing

### Why no single-run option

Stripe charges €0.30 + 2.9% per transaction. On a €0.39 charge you keep €0.08. Minimum viable transaction is ~€3. All pricing is credit packs or subscription.

### Credit packs

| Pack | Price | Credits | Per-run | You keep (after Stripe) |
|---|---|---|---|---|
| Starter | €2.99 | 5 | €0.60 | €2.52 (84%) |
| Standard | €5.99 | 15 | €0.40 | €5.41 (90%) |
| Value | €9.99 | 30 | €0.33 | €9.40 (94%) |

### Subscription

| Plan | Price | Credits/month | Per-run | Net after Stripe + costs |
|---|---|---|---|---|
| Monthly | €4.99/mo | 20 | €0.25 | ~€4.08/month |

Unused credits roll over, capped at 40. Subscription auto-renews. Users can cancel anytime and keep remaining credits.

### Signup offer

2 free credits on signup. No card required. Email verification required before credits activate.

### Auto-recharge

Users can opt in: when credits drop below X, automatically buy a chosen pack. Stripe charges the saved card. Email notification on every auto-charge.

---

## Revenue Estimation

### Unit economics

| Cost item | Per run |
|---|---|
| LLM (DeepSeek steps 3+8; Gemini free for 3a/3c/5) | ~€0.015 |
| Modal compute (5 min, 2 CPU cores) | ~€0.007 |
| Supabase storage (500KB PDF) | ~€0.001 |
| **Total cost per run** | **~€0.023** |

### Monthly revenue at scale

| Paying users | Gross revenue | Stripe fees | LLM + compute | Infra | Net profit |
|---|---|---|---|---|---|
| 10 | €47 | -€3.76 | -€0.72 | €0 (free tier) | **€42.52** |
| 50 | €235 | -€18.80 | -€3.59 | €0 (free tier) | **€212.61** |
| 100 | €470 | -€37.60 | -€7.18 | -€32 | **€393.22** |
| 500 | €2,350 | -€188 | -€35.88 | -€55 | **€2,071.12** |

Break-even: 12 subscribers OR ~80 credit pack purchases/month.
