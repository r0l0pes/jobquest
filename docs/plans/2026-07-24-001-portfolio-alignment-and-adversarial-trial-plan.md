---
title: "Portfolio Alignment to Resume Variants + Adversarial Trial Economic Re-Eval"
type: feat
status: active
date: 2026-07-24
---

# Portfolio Alignment + Adversarial Trial Re-Eval

**Target repos:** `JobSearch` (adversarial trial findings) and `portifaria` (portfolio edits). All portfolio file paths below are repo-relative to `portifaria/` unless noted; JobSearch paths are repo-relative to `JobSearch/`.

---

## Problem Frame

The July 23 resume market audit (`docs/plans/2026-07-23-resume-market-audit.md`) unified canonical employment dates on both Notion resume variants and added AI-as-gate / evals vocabulary to the Summaries. Two downstream surfaces did not move with the resume:

1. **Published portfolio (`portifaria` `src/constants/experience.ts`)** still renders Fab City Hamburg + HELLA Aglaia Mobile Vision instead of FORVIA HELLA + C&A Brasil, with dates that contradict every resume variant. A recruiter landing on `rodrigolopes.xyz` (the resume's locked header links there) sees a different career history than the PDF.
2. **Cross-family adversarial model trial** (handoff open item #4) was blocked on "requires `OpenAIClient` class or OpenRouter route." Since then GLM-5.2 and Kimi K3 shipped, and the pipeline already wires OpenRouter + AnthropicClient + OpenCode-Go. The blocker is gone and the economics changed.

Scope: align published portfolio surfaces to the locked resume variants, and record the economic verdict for the adversarial trial so the next execution run picks the right cross-family pair.

Non-goals: do not rewrite the resume tailoring pipeline; do not auto-submit applications; do not touch the Notion pages (already applied).

---

## Summary

Two workstreams, one session:

- **Portfolio alignment** — mechanical edits to `portifaria` files bringing published dates, role roster, and AI/evals vocabulary in line with the July 23 resume canonical state.
- **Adversarial trial re-eval** — document the July 24 2026 model-pricing reality and conclude which mix to run.

---

## Scope Boundaries

### In scope

- `portifaria/src/constants/experience.ts` — replace role roster with canonical.
- `portifaria/copy-content/*.md` — align case study header dates.
- `portifaria/src/components/sections/About.tsx` — AI-led "What I do" + evals token.
- `portifaria/src/constants/caseStudies.ts` — Postscript cs1 evals rewrite.
- Adversarial-trial verdict recorded in this plan.

### Deferred to Follow-Up Work

- Anthropic prompt caching wire in `AnthropicClient` (unlocks Opus 5 writer under budget).
- Run M4 head-to-head vs free Gemini on a real job posting.
- The 2 pre-existing `test_salary_benchmarking.py` failures — unrelated, fails on clean checkout.
- German-photo CV template (audit Section F2).
- LinkedIn manual update (user task).

---

## Adversarial Trial Economic Re-Eval (July 24, 2026)

### Pricing snapshot (July 2026)

| Model | In/Out ($/M tok) | Cache | Via (wired?) | Notes |
|---|---|---|---|---|
| DeepSeek V4 Flash | 0.14 / 0.28 | 0.0028 in | `deepseek` yes — `deepseek-chat` now routes here | 284B MoE / 13B active; 1M ctx; non-reasoning (fast); throughput only |
| GPT-5.6 Sol | 5 / 30 | — | OpenRouter yes | Default alias routes to Sol (most expensive) |
| GPT-5.6 Terra | 2.50 / 15 | — | OpenRouter yes | Balanced tier |
| GPT-5.6 Luna | 1 / 6 | — | OpenRouter yes | Cost tier (mid-high reasoning) |
| Claude Opus 5 | 5 / 25 | via prompt caching | AnthropicClient yes | TOP writer (43.3% Frontier-Bench), today's release |
| Claude Fable 5 | 10 / 50 | — | AnthropicClient yes | **DROP** — Opus 5 is half price AND stronger; Fable only wins on cyber/bio dual-use (irrelevant here) |
| Claude Sonnet 5 intro | 2 / 10 | via prompt caching | AnthropicClient yes | Intro until Aug 31, then 3 / 15 |
| GLM-5.2 | 1.40 / 4.40 | — | OpenCode-Go / OpenRouter yes | Open-weight MIT; strong reasoning; "mixed" safety (NIST) |
| Kimi K3 | 3 / 15 | 90% hit → 0.30 in | OpenCode-Go yes | Always-reasoning; tops SWE Marathon; best reviewer |
| Gemini 3 Flash | free | — | GeminiClient yes | Current reviewer primary |
| Gemini 3.1 Flash-Lite | free | — | GeminiClient yes | Current reviewer fallback |

### Per-step pipeline analysis: the pipe has 6 independently-switchable LLM steps

The pipeline already has per-step `*_PROVIDER` / `*_MODEL` env vars wired in `modules/llm_client.py`. Every mix below is a `.env` change, zero new code.

| Step | Env vars | Cognitive demand | Est tokens/app (in/out) | Cheap OK? |
|---|---|---|---|---|
| 1. Scrape | generic `llm` | HTML extraction (very low) | ~6K / 1K | ✅ free Gemini |
| 2b. Fit eval | FIT | Simple classification | ~4K / 0.5K | ✅ free Gemini |
| **3. Tailor resume** | TAILOR | **High writing + reasoning** | ~19K / 8K | ❌ flagship step, spend here |
| 4. Write .tex | generic | Formatting | — | ✅ cheap |
| **5. Adversarial review** | REVIEWER | **High reasoning (different family from step 3)** | ~5K / 3K | ⚠️ reasoning needed, but 1 step only |
| 5b. Apply review | generic | JSON patch | ~6K / 2K | ✅ cheap |
| ATS check | ATS | Keyword extraction | ~6K / 1K | ✅ free Gemini |
| 6. Apply ATS | generic | Structured edit | ~6K / 2K | ✅ cheap |
| **8. Q&A generation** | QA | **High writing quality** | ~10K / 6K | ❌ second-most-visible output |
| **8b. Interview prep** | INTERVIEW | Moderate reasoning, long ctx | ~6K / 4K | ⚠️ Kimi K2.6 default covers this |
| **9. Cover letter** | generic | **High writing quality** | ~6K / 3K | ❌ recruiter-facing |
| Compile inspect | generic | Light fix-up | ~4K / 2K | ✅ cheap |

### Mixed assignments under €35/mo at 120 applications

Cheap/structured steps (1, 2b, 4, 5b, ATS, 6, compile) stay on **free Gemini** in every mix. Budget = €35/mo ≈ $38/mo ≈ $0.32/app. All mixes cross-family adversarial (step 3 writer ≠ step 5 reviewer).

| Mix | Step 3 (Tailor) | Step 5 (Review) | Step 8 (Q&A) | Step 9 (Cover) | 8b (Interview) | $/app | €/mo | Sustained? |
|---|---|---|---|---|---|---|---|---|
| **M1 — Opus flagship** | Opus 5 | Kimi K3 | GLM-5.2 | GLM-5.2 | Kimi K3 | $0.45 | **€50** | ❌ over cap |
| **M1+Cache — Opus (unlock)** | Opus 5 (cached) | Kimi K3 | GLM-5.2 | GLM-5.2 | Kimi K3 | ~$0.28 | **~€31** | ✅ if caching wired |
| **M2 — OpenAI-led** | GPT-5.6 Luna | Kimi K3 | GLM-5.2 | GLM-5.2 | Kimi K3 | $0.22 | **€24** | ✅ sustained |
| **M3 — Anthropic intro** | Sonnet 5 (intro) | Kimi K3 | GLM-5.2 | GLM-5.2 | Kimi K3 | $0.27 | **€30** | ✅ → Aug 31, then €42 |
| **M4 — Zhipu+Moonshot** | **GLM-5.2** | **Kimi K3** | GLM-5.2 | GLM-5.2 | Kimi K3 | $0.21 | **€23** | ✅ sustained, no expiry |

### The Opus 5 caching unlock (M1+Cache)

Add `cache_control: { type: "ephemeral" }` to the system prompt block in `AnthropicClient.generate()`. The master resume (~4K tokens) + voice rules (~1.2K tokens) are identical across all 120 apps. Anthropic's prompt cache (0.1x read vs 1x write) cuts cached input cost ~10x, dropping Opus 5 step 3 from $0.30 → ~$0.14/app and M1 from €50 → ~€31/mo. Even at 50% hit rate lands at ~€35. ~30 min code edit.

### Recommended default: M4 — GLM-5.2 + Kimi K3 (~€23/mo)

Best reviewer in budget (Kimi K3 always-reasoning), both sides reason, €12 headroom for retries. Durable, no Sep 1 cliff, no code change.

```env
TAILOR_PROVIDER=opencode         TAILOR_MODEL=glm-5.2
REVIEWER_PROVIDER=opencode        REVIEWER_MODEL=kimi-k3
QA_PROVIDER=opencode              QA_MODEL=glm-5.2
INTERVIEW_PROVIDER=opencode       INTERVIEW_MODEL=kimi-k3
ATS_PROVIDER=gemini               ATS_MODEL=gemini-3.1-flash-lite
FIT_PROVIDER=gemini               FIT_MODEL=gemini-3.1-flash-lite
```

To switch to M1+Cache (Opus 5 under €35): wire Anthropic caching, then change one env var:

```env
TAILOR_PROVIDER=anthropic        TAILOR_MODEL=claude-opus-5-20260724
```

---

## Key Technical Decisions

1. **Roles in `experience.ts`: Postscript → FORVIA HELLA → Accenture → C&A Brasil.** Decided by user. Matches resume canonical and the four `caseStudies.ts` cards.
2. **Canonical dates** (locked on Notion, applied 2026-07-23): Postscript Jul 2024 – Jun 2026; FORVIA HELLA Nov 2022 – May 2024; Accenture Jun 2020 – Aug 2022; C&A Brasil Aug 2018 – May 2020; Education 2017.
3. **Case study headers align to canonical role tenure.** Role-level case studies (Postscript, FORVIA, Accenture) take the full canonical dates. C&A sub-initiative studies take canonical tenure in header; body keeps initiative-specific durations (they describe work scope, not employment).
4. **AI-led "What I do" paragraph adopted** from the May 26 portfolio handoff A/B candidate.
5. **Evals vocabulary surfaced** in Postscript cs1 approach bullet 1 and About methodologies list.
6. **Cross-family trial rerouted** from single-pair (GPT+Claude) to per-step mixed assignments. Default: M4 (GLM-5.2 + Kimi K3, ~€23/mo sustained). Premium unlock: M1+Cache (Opus 5 + Kimi K3, ~€31/mo) requires Anthropic caching wire.

---

## Implementation Units

### U1. experience.ts — role roster + canonical dates

**Goal:** Replace the 4-role experience array to match resume canonical history.

**Files:** `src/constants/experience.ts`

**Dependencies:** none.

**Approach:** Rewrite to 4 entries: Postscript (Jul 2024 – Jun 2026, Growth & AI), FORVIA HELLA (Nov 2022 – May 2024, Senior PM), Accenture (Jun 2020 – Aug 2022, Digital PM), C&A Brasil (Aug 2018 – May 2020, PM). Bullets from matching case studies. No em dashes.

**Test scenarios**

- Happy path: array length 4, order Postscript → FORVIA → Accenture → C&A.
- Edge case: no bullet contains em dash (`—`); uses commas/hyphens.
- Integration: `tsc --noEmit` clean; `ExperienceItem` shape preserved.

**Verification:** `npx tsc --noEmit` passes.

---

### U2. Case study header dates aligned to canonical

**Goal:** Bring all `copy-content/*.md` headers in line with locked resume dates.

**Files:** `copy-content/postscript_case_study.md`, `copy-content/FORVIA_HELLA_Case_Study.md`, `copy-content/accenture_case_study.md`, `copy-content/case_study_ca_brasil_checkout.md`, `copy-content/case_study_ca_brasil_combined.md`, `copy-content/case_study_ca_brasil_whatsapp.md`

**Dependencies:** U1.

**Approach:** Edit header line 2 of each file to canonical tenure dates. C&A body text keeps initiative durations.

**Verification:** `grep -En '\| (Jan\|Feb\|Mar...) [0-9]{4} –' copy-content/*.md` shows canonical dates.

---

### U3. About.tsx — AI-led "What I do"

**Goal:** Align portfolio About with resume AI-as-gate Summary.

**Files:** `src/components/sections/About.tsx`

**Dependencies:** U1.

**Approach:** Replace two "What I do" paragraphs with AI-led version: lead with 8+ years Growth PM, then second paragraph specialising in AI-powered features (conversational, LLM workflows, personalization engines) alongside structured experimentation.

**Verification:** dev build renders AI-led paragraph; keyword `AI` in About copy.

---

### U4. caseStudies.ts — Postscript cs1 evals rewrite

**Goal:** Surface evals vocabulary in flagship case study, matching resume rewording.

**Files:** `src/constants/caseStudies.ts`

**Approach:** Rewrite cs1 approach[0].description to include "evaluating variant quality against brand guidelines and live performance data" — language from resume Postscript bullet.

**Verification:** cs1 approach[0].description contains the evals phrase.

---

### U5. About.tsx methodologies — evals token + growth loops token

**Goal:** Add evals vocabulary + growth loops token to portfolio.

**Files:** `src/components/sections/About.tsx`

**Dependencies:** U3.

**Approach:** Add `Eval Frameworks` to `methodologies` array, `Growth Loops` to `coreSkills`.

**Verification:** dev build shows evals chip in Tools & Methodologies.

---

### U6. Stale file cleanup

**Goal:** Remove archived WFP case study source.

**Files:** `copy-content/wfp_case_study_final.md` (delete)

**Approach:** Delete file. Confirm no live `src/` import references it.

**Verification:** file absent; `grep -rn 'WFP\|wfp' src/` returns nothing.

---

### U7. Adversarial trial — record verdict

**Goal:** Record the July 24 findings in the plan itself (this document).

**Files:** This document. (The July 23 audit doc's open items are superseded by this plan's Adversarial Trial section.)

---

## System-Wide Impact

- **Recruiter-facing:** `rodrigolopes.xyz` Experience section, About copy, and flagship case study now match the resume PDF.
- **LLM cost:** default mix M4 (GLM-5.2 + Kimi K3) at ~€23/mo vs previous premium estimate of ~€0.30-0.60/app. Budget headroom for retries.
- **No pipeline code changed** for M2/M3/M4 — all env-var only. M1+Cache requires ~30 min AnthropicClient edit.

## Risks

| Risk | Mitigation |
|---|---|
| C&A body references 4-month pilot, header shows 22-month tenure | Header is employment metadata; body describes the initiative. Defensible. |
| GLM-5.2 "mixed" NIST safety | No untrusted external content through GLM-5.2; reviewer gate (Kimi K3) upstream. |
| Kimi K3 always-reasoning billing surprise | Reserve for single review step only; monitor first run. |
| Opus 5 caching estimate unverified | Even at 50% cache hit rate, M1+Cache lands at ~€35 cap. |

## Deferred Questions

- Exact OpenCode-Go model aliases for GLM-5.2 / Kimi K3 — confirm at execution time.
- Anthropic prompt caching wiring in `AnthropicClient` — ~30 min, unlocks premium tier.
