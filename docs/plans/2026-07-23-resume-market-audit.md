---
title: "Resume Market Audit — All 3 Variants vs. Refreshed DE/ES Research"
type: analysis
status: applied
date: 2026-07-23
---

# Resume Market Audit — July 2026

Audit of the Growth, Generalist, and AI-PM resume variants against:

- `JobSearch-Planning/personal/market_research_growth_pm_de_es_2026.md` (Feb 2026, refreshed with July 2026 update section today)
- `portifaria/copy-content/builder_pm_research.md` (Jun 2026)

**Verdict: the resume is structurally up to date, but the market moved underneath it in one big way — AI went from "differentiator" (30–40% of JDs in Feb) to "gate" (61% of postings in July). The Summaries have not caught up. Plus several cross-variant inconsistencies that look like bugs, not strategy.**

---

## A. Critical: Cross-Variant Inconsistencies (fix regardless of market)

These contradict each other across the two Notion pages. Any recruiter who sees both (or a tracker entry with different dates) will flag it.

| Field | Growth page (2f40fd98) | Generalist page (30b0fd98) | Action |
|---|---|---|---|
| FORVIA HELLA dates | Nov 2022 – May 2024 | Jul 2022 – Jan 2024 | **Rodrigo: confirm true dates, unify** |
| Accenture dates | Jun 2020 – Aug 2022 | Feb 2020 – Apr 2022 | **Confirm true dates, unify** |
| C&A dates | Aug 2018 – May 2020 | Mar 2018 – Jan 2020 | **Confirm true dates, unify** |
| Education year | 2017 | 2016 | **Confirm, unify** |
| Phone | +4915203590361 | +49 0172 5626057 | **Two different numbers — pick one** |

Note: a gap between C&A end and Accenture start appears only in the Generalist dates (Jan 2020 → Feb 2020 is clean; May 2020 → Jun 2020 is clean). Both work, but they must match.

## B. The 61% AI Gate (biggest market shift)

Feb research: AI in 30–40% of senior Growth PM JDs = differentiator.
July refresh: **61% of PM postings require AI experience.** AI is now a screening gate.

Current state: both variants carry strong AI evidence, but only in the Postscript job title ("Growth & AI"), the Postscript bullets, and the Technical Proficiency section. **Neither Summary mentions AI.** A recruiter skimming the top third sees "Senior Growth Product Manager... conversion, activation, retention" — pre-2026 framing.

**Recommended changes:**

| # | Variant | Change | Rationale |
|---|---|---|---|
| B1 | Growth | Summary: add AI clause, e.g. "...retention across B2C e-commerce, B2B self-serve platforms, and digital products in Europe and LatAm — most recently leading **AI-powered growth products** (generative AI experimentation, predictive analytics) at Postscript." | Passes AI gate in first 3 lines. Verifiable from Postscript bullets. |
| B2 | Generalist | Summary: add AI clause, e.g. "...delivery across B2C e-commerce, B2B platforms, and digital products — including **AI-powered messaging and experimentation products** used by 18,000+ merchants." | Same gate, generalist framing. |
| B3 | AI-PM | Variant is broken at the pipeline level — see section D. | — |

## C. Evals Vocabulary (new #1 interview topic)

July research: the biggest gap between what candidates prepare and what companies ask is **evals (evaluation frameworks)**, cost-latency-quality tradeoffs, model selection.

Current Postscript bullet says: "Used predictive analytics and generative AI to test hundreds of variants per automation... through continuous model learning."

The underlying work (scoring variants against control, quality bar via brand guidelines) IS evaluation. Honest rewording available without fabrication:

| # | Change | Before → After |
|---|---|---|
| C1 | Postscript bullet 1 (both variants) | "...driving a 28% increase in earnings-per-message... through continuous model learning." → "...**evaluating variant quality against brand guidelines and live performance data**, driving a 28% increase in earnings-per-message through continuous model learning." |
| C2 | Technical Proficiency (both variants) | Add `Eval Frameworks` or `LLM Output Evaluation` to the AI-Assisted & Agentic Workflows line, next to "ML Use Case Discovery and Validation" | Only if Rodrigo confirms this is fair — the vocabulary claim, not a new skill. |

## D. AI-PM Variant Is Silently Broken

- `web_ui.py` maps "AI-PM" to the same Notion page as Growth PM (`2f40fd98`).
- The differentiation comes from `research/ai_pm_context.md` injected at pipeline time — **that file does not exist.** `_load_ai_pm_context()` returns `""` silently.
- So every "AI-PM" run since the file was lost has produced a Growth resume with an AI-PM tagline and QA framing, no AI context.

**Options:**

1. **Recreate `research/ai_pm_context.md`** from `portifaria/copy-content/builder_pm_research.md` (it contains the exact positioning, honest-framing rules, and recommended bullets — likely the original source). ~30 min.
2. Create a dedicated AI-PM Notion page as a real third variant (bigger job, more maintenance).
3. Retire the AI-PM toggle and rely on Growth + AI-in-summary (simplest).

Recommend option 1 now, option 2 later if AI-titled roles become the primary target.

## E. ATS Keyword Gaps (Feb list, re-verified)

Checked against both Notion pages:

| Keyword | Growth | Generalist | Fix |
|---|---|---|---|
| A/B testing, funnel analysis, PLG, experimentation, activation, onboarding, North Star Metric, OKRs, SQL, Amplitude, stakeholder | ✓ | ✓ | — |
| Mixpanel | ✓ | ✗ (has Looker instead) | Add to Generalist if true |
| `agile` | ✗ | ✗ | Low priority — add "agile" to a Tools/ways-of-working phrase only if natural |
| `growth loops` | ✗ | ✗ | Medium priority — Postscript re-engagement automation and opt-in work are loop-shaped; can be added honestly to Summary or Postscript bullet 3 |
| `user retention` (exact phrase) | partial | partial | Bullets say "retention" — acceptable; ATS stemming usually catches it |

## F. Smaller Items

1. **Generalist variant AI section is weaker than Growth's**: lacks Cursor, n8n, PostHog, Prompt Engineering, LLM Workflows (has GitHub Copilot, ChatGPT/Claude/Gemini instead). Recommend syncing the tools lists so both reflect current reality.
2. **Germany convention**: Feb research notes German-HQ companies still expect a photo on the CV. Current PDF template has none. Optional: only relevant when targeting German-native (non-startup) companies. Park unless targeting those.
3. **Spain**: Spanish (C1) already listed — good. No change needed; Spain remains opportunistic secondary market.
4. **Taglines**: Growth "Experiments that accelerate revenue." ✓ holds. Generalist "E2E ownership that delivers measurable outcomes." — consider integrator framing ("Connects engineering, design, and go-to-market into shipped outcomes") given the Builder/Integrator split, but low priority.

---

## Proposed Execution Order

1. **Rodrigo confirms** true employment dates + phone number (Section A) — blocker for everything else.
2. Recreate `research/ai_pm_context.md` (Section D, option 1) — I can do this from the builder research doc.
3. Apply B1, B2 (Summary AI clauses) + C1 (eval language) to both Notion pages.
4. Sync Technical Proficiency lists (F1) + C2 if approved.
5. Decide on `growth loops` wording (E).
6. Run `pytest tests/ -v` and a `--dry-run` to verify pipeline still healthy.

Nothing above fabricates content — every change is reframing of verified work or vocabulary alignment. The reviewer step (Step 6) will still guard each tailored output.

---

## Changelog — Applied 2026-07-23

| Item | Status | Notes |
|---|---|---|
| Notion Growth page (2f40fd98) | Applied | Summary AI rewrite, Postscript bullets 1+3, Jun 2026 end date, Location→12435 Berlin, phone deleted, Tech Proficiency additions |
| Notion Generalist page (30b0fd98) | Applied | Summary AI rewrite, Postscript bullets 1+3, Jun 2026 end date, canonical dates unified, Education 2017, Location→12435 Berlin, phone deleted, Tech Proficiency sync |
| `research/ai_pm_context.md` | Recreated | Builder PM research + July evals gate. Smoke tests pass. |
| `modules/pipeline.py` locked header | Updated | Dropped LinkedIn + phone; now website | email | 12435 Berlin |
| `prompts/qa_generator.md` phone reference | Unchanged | Line 212 still references phone — non-blocking, template text not touched by pipeline header injection. Flag for future cleanup. |
| Pre-existing test failures | 2 | `tests/test_salary_benchmarking.py::TestSalaryInQA` — mock patch mismatch after per-step client factory refactor. Unrelated to this session; fails on clean checkout too. |
