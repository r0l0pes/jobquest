# LLM Model Comparison for JobQuest Pipeline Steps 3, 6, and 8

**Date:** 2026-07-05
**Scope:** Compare frontier LLMs for resume tailoring (Step 3), adversarial review (Step 6), and ATS keyword check (Step 8). Include models initially overlooked and evaluate whether their premium pricing is justified for this specific pipeline.

---

## Token Volume Per Application

Derived from prompt sizes and pipeline logic in `modules/pipeline.py` and `prompts/`.

| Step | Task | Input Tokens | Output Tokens |
|------|------|-------------|---------------|
| **3a** | JD Analysis | ~3,500 | ~500 |
| **3b** | Targeted Edits (default mode) | ~5,000 | ~600 |
| **3c** | Brief Compliance Check | ~2,500 | ~400 |
| **6** | Adversarial Review | ~7,000 | ~2,500 |
| **8** | ATS Check | ~5,000 | ~2,500 |
| **TOTAL** | | **~23,000** | **~6,500** |

*Note: If `TARGETED_EDITS=1` fails and falls back to full LaTeX generation, Step 3b output balloons to ~6,000 tokens, adding ~$0.10–0.30 per app depending on model.*

---

## Model Rankings 1–5 Per Step

### Step 3 — Resume Writing / Prose / LaTeX Generation

*Task: Write natural LaTeX prose, follow strict voice rules (`rodrigo-voice-lite.md`), preserve all facts and metrics, insert keywords naturally, never fabricate.*

| Rank | Model | Why |
|------|-------|-----|
| **1** | **Claude Opus 4.8** | Best prose quality (9.3/10 EQ-Bench), most human-like output, **least likely to fabricate metrics** — critical for the "never fabricate" rule in `prompts/resume_tailor.md` |
| **2** | **GPT-5.5** | #1 on some creative writing benchmarks, warm natural tone, strong instruction following. **Caveat:** documented tendency to invent metrics not in source material |
| **3** | **Claude Sonnet 5** | New mid-tier that leapfrogs GPT-5.5 on directly comparable benchmarks. Excellent writing + reasoning balance at 40% lower cost than Opus |
| **4** | **Kimi K2.6** | Strong long-context writer (262K), good coherence across long documents. Very cheap via OpenRouter |
| **5** | **GLM-5.2** | Open-weight frontier, beats GPT-5.5 on SWE-bench at 1/6 the cost. Strong writing capability |

### Step 6 — Adversarial Review / Critique / Fact-Checking

*Task: Catch fabrications, missed keywords, tone mismatches, generic content, voice misalignment. Must be critical and honest — not agreeable.*

| Rank | Model | Why |
|------|-------|-----|
| **1** | **Claude Opus 4.8** | Most conservative/honest model available. Adversarial test tied for first (77.1%). Will flag issues rather than say "looks good" |
| **2** | **Claude Sonnet 5** | Excellent reasoning (SWE-bench Pro 63.2%), less agreeable than GPT. Best critique quality per dollar |
| **3** | **Kimi K2.6** | Strong reasoning model, autonomous coding capability implies good error detection. Good at finding inconsistencies across long context |
| **4** | **GPT-5.5** | Strong reasoning but can be **too agreeable/confirmatory** — may miss issues to be "helpful". Less reliable for adversarial critique |
| **5** | **Gemini 3.1 Pro** | Good reasoning and data analysis. Large context (1M tokens) helpful for cross-referencing draft vs master resume. Technically precise |

### Step 8 — ATS Check / Analytical Extraction / Structured JSON

*Task: Extract keywords from JD, classify coverage (COVERED / SEMANTIC / LOW_VIS / MISSING / N/A), output strict JSON + markdown report.*

| Rank | Model | Why |
|------|-------|-----|
| **1** | **Claude Sonnet 5** | Best structured output reliability + reasoning balance. Good at following strict classification rules without drifting |
| **2** | **GPT-5.5** | Reliable JSON mode, strong analytical extraction. Good semantic matching between JD and resume |
| **3** | **Gemini 3.1 Pro** | Technically precise, data-analysis strength. Large context (1M tokens) handles long JDs easily |
| **4** | **Qwen 3.7-Plus** | Top-ranked for long-context comprehension and retrieval. Excellent for side-by-side document comparison |
| **5** | **DeepSeek V4-Pro** | Strong reasoning, reliable structured output, 1M context window. Very cheap |

---

## Cost Per Application & Monthly Spend

Formula: `(23,000 / 1,000,000 × input_price) + (6,500 / 1,000,000 × output_price)`

### Frontier Tier

| Model | Input $/1M | Output $/1M | Cost/App | 40 Apps/Mo | 100 Apps/Mo |
|-------|-----------|-------------|----------|------------|-------------|
| **Claude Mythos 5** | $10.00 | $50.00 | **$0.555** | **$22.20** | **$55.50** |
| **Claude Opus 4.8** | $5.00 | $25.00 | $0.278 | $11.10 | $27.75 |
| **GPT-5.6 Sol** | $5.00 | $30.00 | $0.310 | $12.40 | $31.00 |
| **GPT-5.5** | $5.00 | $30.00 | $0.310 | $12.40 | $31.00 |
| **Gemini 3.5 Pro** (est.) | $13.50 | $40.50 | $0.574 | $22.96 | $57.40 |
| **Claude Sonnet 5** | $3.00 | $15.00 | $0.167 | $6.66 | $16.65 |
| **GPT-5.6 Terra** | $2.50 | $15.00 | $0.155 | $6.20 | $15.50 |

### Budget Tier

| Model | Input $/1M | Output $/1M | Cost/App | 40 Apps/Mo | 100 Apps/Mo |
|-------|-----------|-------------|----------|------------|-------------|
| **Gemini 3.1 Pro** | $2.00 | $12.00 | $0.124 | $4.96 | $12.40 |
| **Gemini 3.5 Flash** | $1.50 | $9.00 | $0.093 | $3.72 | $9.30 |
| **GPT-5.6 Luna** | $1.00 | $6.00 | $0.062 | $2.48 | $6.20 |
| **GLM-5.2** (OpenRouter) | $0.93 | $3.00 | $0.041 | $1.64 | $4.09 |
| **Kimi K2.6** (OpenRouter) | $0.67 | $3.42 | $0.038 | $1.51 | $3.76 |
| **DeepSeek V4-Pro** | $1.74 | $3.48 | $0.063 | $2.50 | $6.26 |
| **DeepSeek V4-Flash** | $0.14 | $0.28 | $0.008 | $0.32 | $0.80 |

---

## Why Claude Mythos 5, GPT-5.6, and Gemini 3.5 Omni Were Not Initially Listed

### Claude Mythos 5

- **Availability:** Restricted to a closed Anthropic program called **"Project Glasswing."** Not available via standard API unless you are an approved security partner.
- **Pricing:** **$10/$50 per 1M tokens** — double the price of Opus 4.8 ($5/$25).
- **What it is:** Same core model as Claude Fable 5, but **without safety classifiers**. Fable 5 itself was only restored to global API access on July 1, 2026, after a U.S. export control order was lifted.
- **Verdict for pipeline:** If you can get access, Mythos 5 is likely the best adversarial reviewer (Step 6) because it won't hold back critique. But at 2× Opus pricing and restricted access, it is not a practical default recommendation.

### GPT-5.6

- **Availability:** Announced June 26, 2026, but in a **government-gated preview** available to only ~20 approved partner organizations. Not available in ChatGPT or standard API.
- **Pricing (when available):**
  - **Sol** (flagship): $5/$30 — same price as GPT-5.5
  - **Terra** (balanced): $2.50/$15 — cheaper than GPT-5.5
  - **Luna** (fast): $1/$6 — very cheap
- **Performance:** Sol Ultra scored 91.9% on Terminal-Bench 2.1, ahead of Claude Mythos 5 (88.0%) and GPT-5.5 (88.0%).
- **Verdict for pipeline:** Terra at $2.50/$15 would be an excellent value replacement for GPT-5.5 once broadly available. But right now you cannot use it. Luna at $1/$6 would be the cheapest frontier-class option if it maintains quality.

### Gemini 3.5 Omni

- **What it actually is:** **Gemini Omni Flash** is a **video generation and editing model** released June 30, 2026. It does conversational video editing via natural language. It is not a text-generation model.
- **Pricing:** $1.50/1M input tokens, $17.50/1M video output tokens.
- **Verdict for pipeline:** **Not applicable.** This is a video model. For text-based resume processing, it is irrelevant. There is no "Gemini 3.5 Omni" text model.

---

## Are the Newer Models Worth the Premium?

### Claude Mythos 5 vs. Claude Opus 4.8

| Factor | Mythos 5 | Opus 4.8 | Worth it? |
|--------|----------|----------|-----------|
| Cost per app | $0.555 | $0.278 | **2× more expensive** |
| Access | Closed program | Standard API | **You probably can't get it** |
| Step 3 (Writing) | Same core as Fable 5 — marginally better prose | Already #1 | **No** — Opus is sufficient |
| Step 6 (Review) | No safety filters = more blunt critique | Already most conservative | **Maybe** — if you have access, test it |
| Step 8 (ATS) | Overkill | Overkill | **No** — use Sonnet 5 or cheaper |

**Bottom line:** Mythos 5 costs 2× Opus for what is likely a marginal improvement in resume prose. The lack of safety filters *could* make it a better adversarial reviewer, but you cannot rely on a model you cannot access. Stick with Opus 4.8 for Step 3, Sonnet 5 for Steps 6 and 8.

### GPT-5.6 vs. GPT-5.5

| Factor | GPT-5.6 Sol | GPT-5.6 Terra | GPT-5.5 | Worth it? |
|--------|-------------|---------------|---------|-----------|
| Cost per app | $0.310 | $0.155 | $0.310 | Terra is **half the price** |
| Availability | Gated preview | Gated preview | Available now | **Not yet usable** |
| Step 3 (Writing) | Likely better | Likely comparable | Good, but fabricates metrics | **Wait for Terra** — half price, probably same quality |
| Step 6 (Review) | Same price as 5.5 | Cheaper | Too agreeable | **No** — use Claude instead |
| Step 8 (ATS) | Overpriced | Good value | Good | **Terra will be best value** when available |

**Bottom line:** GPT-5.6 Terra at $2.50/$15 will be the best-value GPT-class model for this pipeline once it launches. Sol is pointless — same price as GPT-5.5. Luna at $1/$6 is intriguing for high-volume ATS checks if quality holds up.

### Gemini 3.5 Flash vs. Gemini 3.1 Pro

| Factor | Gemini 3.5 Flash | Gemini 3.1 Pro | Worth it? |
|--------|------------------|----------------|-----------|
| Cost per app | $0.093 | $0.124 | **25% cheaper** |
| Context | 1M tokens | 1M tokens | Same |
| Speed | 20% faster | Baseline | Yes |
| Step 3 (Writing) | Better agentic capabilities | Lower creative writing scores | **Yes** — upgrade if staying in Gemini ecosystem |
| Step 6 (Review) | Better reasoning | Good | **Yes** |
| Step 8 (ATS) | Excellent structured output | Good | **Yes** |

**Bottom line:** Gemini 3.5 Flash is **both better and cheaper** than Gemini 3.1 Pro. If you want to stay on Gemini, this is a no-brainer upgrade. Your current default `gemini-3.1-flash-lite` should be replaced with `gemini-3.5-flash` for the paid tier, or kept as the free-tier fallback.

### Gemini 3.5 Pro (Estimated) vs. Gemini 3.5 Flash

| Factor | Gemini 3.5 Pro (est.) | Gemini 3.5 Flash | Worth it? |
|--------|----------------------|------------------|-----------|
| Cost per app | $0.574 | $0.093 | **6× more expensive** |
| Context | 2M tokens | 1M tokens | Resume processing doesn't need 2M |
| Step 3 (Writing) | Likely best Gemini writer | Good enough | **No** — 6× cost for marginal prose gain |
| Step 6 (Review) | Excellent | Good | **No** — Claude Sonnet 5 is better and cheaper |
| Step 8 (ATS) | Overkill | Excellent | **No** |

**Bottom line:** Gemini 3.5 Pro is estimated to cost 6× more than 3.5 Flash. For resume processing — where the output is a 1–2 page LaTeX document — the 2M context window and marginal reasoning gains are completely unnecessary. Do not use this.

---

## Recommended Configurations

### Option A: Best Quality (Unlimited Budget)

```
Step 3 (Writing):    Claude Opus 4.8    ($0.278/app)
Step 6 (Review):     Claude Opus 4.8    ($0.278/app)
Step 8 (ATS):        Claude Sonnet 5    ($0.167/app)
```

**Monthly cost:** $11.10 (40 apps) / $27.75 (100 apps)

### Option B: Best Value (Recommended)

```
Step 3 (Writing):    Claude Sonnet 5    ($0.167/app)
Step 6 (Review):     Claude Sonnet 5    ($0.167/app)
Step 8 (ATS):        Claude Sonnet 5    ($0.167/app)
```

**Monthly cost:** $6.66 (40 apps) / $16.65 (100 apps)

*Sonnet 5 is #3 writer, #2 reviewer, and #1 at structured ATS output. The quality drop from Opus is marginal; the cost drop is 40%.*

### Option C: Ultra-Budget with Quality

```
Step 3 (Writing):    Kimi K2.6 or GLM-5.2    ($0.038–0.041/app)
Step 6 (Review):     Claude Sonnet 5          ($0.167/app)
Step 8 (ATS):        DeepSeek V4-Flash        ($0.008/app)
```

**Monthly cost:** ~$3.50 (40 apps) / ~$8.75 (100 apps)

*Don't cheap out on Step 6 — adversarial review is where quality matters most. The writing step can tolerate a cheaper model if you validate output. The ATS step is a structured extraction task that even small models handle well.*

### Option D: Gemini-Only Upgrade Path

```
Step 3 (Writing):    Gemini 3.5 Flash    ($0.093/app)
Step 6 (Review):     Gemini 3.5 Flash    ($0.093/app)
Step 8 (ATS):        Gemini 3.5 Flash    ($0.093/app)
```

**Monthly cost:** $3.72 (40 apps) / $9.30 (100 apps)

*If you prefer to stay in the Google ecosystem, 3.5 Flash is both better and 25% cheaper than 3.1 Pro. Keep 3.1 Flash-Lite as your free-tier fallback.*

---

## Code Changes Required

Your `modules/llm_client.py` already supports per-provider model selection via env vars. To implement these recommendations, the minimal changes are:

1. **Update `WRITING_CHAIN`** to include newer models in priority order:

   ```python
   WRITING_CHAIN = [
       ("anthropic", "claude-opus-4-8",       "Claude Opus 4.8",     0),
       ("anthropic", "claude-sonnet-5",       "Claude Sonnet 5",       0),
       ("gemini",    "gemini-3.5-flash",      "Gemini 3.5 Flash",      0),
       # ... existing fallbacks
   ]
   ```

2. **Add `REVIEWER_PROVIDER` / `REVIEWER_MODEL`** env var support in `create_reviewer_client()` — currently hardcoded to Gemini. The reviewer should use a different model family from the drafter (adversarial principle).

3. **Add `ATS_PROVIDER` / `ATS_MODEL`** env var support for Step 8 if you want to route ATS checks to a cheaper model than the writing chain.

---

## Summary Table: Worth It or Not?

| Model | vs. Earlier Model | Worth It for Pipeline? | Why |
|-------|-------------------|------------------------|-----|
| **Claude Mythos 5** | Opus 4.8 | **No** (mostly) | 2× price, restricted access. Only worth testing for Step 6 if you can get access. |
| **GPT-5.6 Sol** | GPT-5.5 | **No** | Same price, not available. |
| **GPT-5.6 Terra** | GPT-5.5 | **Yes — when available** | Half the price, likely same or better quality. Best future GPT option. |
| **GPT-5.6 Luna** | DeepSeek V4-Flash | **Maybe** | Cheap frontier-class. Test when available for Step 8. |
| **Gemini 3.5 Omni** | N/A | **N/A** | Video model, not applicable to text pipeline. |
| **Gemini 3.5 Pro** | Gemini 3.5 Flash | **No** | 6× price for marginal gains. Overkill for 1–2 page resumes. |
| **Gemini 3.5 Flash** | Gemini 3.1 Pro | **Yes** | Better quality, 25% cheaper. Immediate upgrade if you use Gemini. |

---

## Session Decisions (2026-07-05)

**Chosen configuration for ~100 applications/month:**

| Step | Console Label | Function | Model | Cost/App |
|------|--------------|----------|-------|----------|
| **2b** | Fit Evaluation | `step_evaluate_fit` | DeepSeek V4-Pro | $0.0078 |
| **3** | Tailor Resume | `step_tailor_resume` (3a+3b+3c) | Claude Opus 4.8 | $0.1175 |
| **5** | Reviewer | `step_review_drafts` | Claude Sonnet 5 | $0.0585 |
| **5/9** | ATS Check | `step_ats_check` | DeepSeek V4-Pro | $0.0174 |
| **8** | Q&A + Cover Letter | `step_generate_qa` | Claude Opus 4.8 | $0.115 |
| **8b** | Interview Prep | `step_generate_interview_prep` | Kimi K2.6 | $0.0115 |
| | | | **TOTAL** | **$0.328** |

**Monthly cost at 100 applications: ~$32.77/month**

Alternative using **Sonnet 5 for Step 3** (instead of Opus): ~$28.07/month. User to decide whether the $4.70/month premium for Opus on tailoring is worth it.

---

### Key Architecture Findings

1. **Current client functions are insufficient for the desired split:**
   - `_get_fit_client()` — hardcoded to Gemini 3.1 Flash-Lite
   - `_get_writing_client()` — shared by Steps 3, 8 (Q&A), and 8b (Interview)
   - `_get_reviewer_client()` — hardcoded to Gemini fallback
   - `step_ats_check` receives a general `llm` param from `apply.py` — currently Gemini with cross-provider fallback

2. **Steps 8 and 8b cannot have different models without code changes** because both call `_get_writing_client()`. The handoff plan must account for either:
   - Adding `create_qa_client()` and `create_interview_client()` functions
   - Or accepting the same model for both steps

3. **Cover letter does NOT need a separate LLM call.** It is generated within Step 8 (`step_generate_qa`) as the first "question" in the combined prompt. `step_compile_cover_letter` (Step 9/10) just fills a LaTeX template with the already-generated text.

4. **Step 3 consists of 3 sub-calls** (3a JD analysis, 3b targeted edits, 3c compliance check) all using the same writing client. They can be treated as a single "unit" for model assignment.

---

### Why Not All Steps Use Frontier Models

Not every pipeline step needs a frontier model. The split is driven by task type:

| Task Type | Needs | Examples | Cheaper Model OK? |
|-----------|-------|----------|-------------------|
| **Creative writing / prose** | Voice, naturalness, no fabrication | Steps 3, 8 | ❌ Use Claude |
| **Adversarial critique** | Honesty, non-agreeableness | Step 5 | ❌ Use Claude |
| **Structured JSON / classification** | Schema compliance, extraction | Steps 2b, ATS | ✅ DeepSeek/Kimi |
| **Template-heavy generation** | STAR matching, likely questions | Step 8b | ✅ Kimi/GLM |

**Open-weight models (Kimi K2.6, GLM-5.2, DeepSeek) are interchangeable for structured tasks but NOT for creative writing or adversarial review.** Research shows open models tend to be more agreeable/confirmatory and less reliable at catching fabrications.

---

### Code Changes Required

1. **Add per-step env var support** in `modules/llm_client.py`:
   - `FIT_PROVIDER` / `FIT_MODEL` for `_get_fit_client()`
   - `REVIEWER_PROVIDER` / `REVIEWER_MODEL` for `_get_reviewer_client()`
   - `ATS_PROVIDER` / `ATS_MODEL` for Step 8 (`step_ats_check`)
   - Either split `_get_writing_client()` into `create_tailor_client()` and `create_qa_client()`, or accept Sonnet 5 for both Steps 3 and 8
   - `INTERVIEW_PROVIDER` / `INTERVIEW_MODEL` for Step 8b

2. **Update `apply.py`** to accept new CLI flags:
   - `--fit-model`
   - `--reviewer-model`
   - `--ats-model`
   - `--interview-model`

3. **Update `WRITING_CHAIN`** to include newer models (already documented above).

---

### What Was Decided NOT to Do (as of 2026-07-05)

- **Split cover letter into its own LLM call.** The cover letter is generated within Step 8's Q&A call. The user confirmed this is fine — no separate Opus call needed just for the cover letter.
- **Use Claude Mythos 5.** Restricted to Anthropic's "Project Glasswing" closed program. Not practically available.
- **Wait for GPT-5.6 Terra.** Gated preview, not usable yet. Will revisit when broadly available.
- **Use Gemini 3.5 Omni.** Video generation model, irrelevant for text pipeline.

---

## Challenge Update — 2026-07-09

**Trigger:** User asked to challenge the top "use Anthropic" recommendation, specifically whether the latest Anthropic model still holds for high-level tasks and whether GPT could take the other tasks. Research re-run as of today, 2026-07-09.

### What changed in the 4 days since the July 5 doc

1. **GPT-5.6 went from "gated, not usable" to GA TODAY.** OpenAI's July 8 post set a July 9 public launch for the full Sol/Terra/Luna family. The July 5 verdict ("wait, not usable yet") is now stale:

   | GPT-5.6 tier | Price (in/out per 1M) | Position | Status 2026-07-09 |
   |-------------|----------------------|----------|-------------------|
   | Sol | $5 / $30 | Flagship (Ultra mode w/ subagents) | GA today |
   | Terra | $2.50 / $15 | "GPT-5.5 perf at 2× lower cost" | GA today |
   | Luna | $1 / $6 | Fast, low-cost | GA today |

   Caveat: METR flagged the highest detected-cheating rate of any public model on its Time Horizon 1.1 suite — an autonomous-coding concern, not a resume-writing one, but worth knowing.

2. **Sonnet 5's "40% cheaper" framing is misleading for some workloads.** Artificial Analysis found Sonnet 5 burns ~40% more output tokens and ~3× more agent loops than Sonnet 4.6, making it cost ~$2.29/task vs Opus 4.8's ~$1.97/task on agentic knowledge work — *more expensive per task than Opus despite cheaper token rates*. For the pipeline's single-shot calls (not multi-loop agents) this penalty is smaller, but the "Sonnet 5 is the value pick" claim is not as clean as the doc presents.

3. **Claude Fable 5 is now generally available** (restored to global API July 1 after the U.S. export-control order was lifted) at $10/$50 — the tier above Opus. Mythos 5 (the no-safety-classifier sibling) remains restricted to Project Glasswing.

### Does the latest Anthropic model hold for high-level tasks? — YES

The two high-level tasks are resume tailoring (Step 3) and adversarial review (Step 5). Anthropic wins both, for reasons the July 5 doc got right and new evidence reinforces:

- **Fabrication (the #1 pipeline rule: "never fabricate"):** Opus 4.8 is documented as 4× less likely than its predecessor to let flawed content pass without flagging it. GPT-5.5 has a documented tendency to invent metrics not in source material. For a pipeline whose core rule is never fabricating resume content, this is disqualifying for GPT as the writer.
- **Prose quality:** Independent testers found Opus 4.8 writes prose that "sounds like a person thought about it" while GPT-5.5 "sounds like an AI wrote it... slightly-too-formal emails from a template."
- **Adversarial review:** Claude is less agreeable/confirmatory than GPT. GPT-5.5 is criticized as "too agreeable — may miss issues to be helpful." A reviewer that wants to say "looks good" is exactly what you don't want at Step 5.
- **Sonnet 5 beats GPT-5.5 on all 6 directly comparable benchmarks** (SWE-bench Pro 63.2 vs 58.6, HLE w/ tools 57.4 vs 52.2, OSWorld 81.2 vs 78.7, etc.).

**On "latest Anthropic model":** Fable 5 ($10/$50) is the newest/top tier but is 2× Opus for marginal prose gain — not worth it for 1–2 page resumes. Opus 4.8 remains the correct high-level pick. The recommendation here survives the challenge.

### Can GPT take the "other" tasks? — YES, and the July 5 doc is genuinely outdated here

The "other" tasks are the structured/analytical ones the doc routes to DeepSeek V4-Pro, Kimi K2.6, and Gemini. GPT-5.6 Terra and Luna (GA today) are legitimate, arguably stronger replacements:

| Step | Task type | July 5 pick | GPT-5.6 challenge | Verdict |
|------|-----------|-------------|-------------------|---------|
| 2b Fit Evaluation | Structured scoring | DeepSeek V4-Pro ($1.74/$3.48) | GPT-5.6 Luna ($1/$6) | GPT viable — extraction/classification, Luna is cheap frontier-class |
| 8 ATS Check | Structured JSON extraction | DeepSeek V4-Pro | GPT-5.6 Luna ($1/$6) | GPT viable — schema compliance; GPT-5.5 already #2 at ATS in this doc |
| 8 Q&A + Cover | Writing + company research | Claude Opus 4.8 | GPT-5.6 Terra ($2.50/$15) | Borderline — needs decent prose; Terra is fine, Opus writes better. Keep Claude if budget allows; Terra is the value cut. |
| 8b Interview Prep | Template-heavy STAR generation | Kimi K2.6 ($0.67/$3.42) | GPT-5.6 Terra ($2.50/$15) | GPT viable but pricier than Kimi — Kimi is cheaper and good enough for templated output. GPT only wins if Kimi quality dips. |

### The deeper challenge: cross-family adversarial review

The refactor plan (docs/plans/2026-07-05-002-refactor-scraping-llm-seams-plan.md) states the principle: "the reviewer should use a different model family from the drafter (adversarial principle)." The July 5 chosen config violates this — it uses Opus 4.8 for writing AND Sonnet 5 for review, both Anthropic. Same family shares family-level blind spots.

GPT genuinely strengthens the pipeline here, in two possible directions:

- **Option X — GPT writes, Claude reviews (cross-family, fabrication-catch):** Step 3 → GPT-5.6 Terra; Step 5 → Claude Opus 4.8 or Sonnet 5. Argument for: Claude reviewing GPT may catch GPT's invented metrics better than Claude reviewing Claude (no shared biases). True adversarial. Cheaper writing. Argument against: GPT is more likely to fabricate in the first place, so the reviewer works harder. Depends on the reviewer catching everything.
- **Option Y — Claude writes, GPT reviews:** Rejected. GPT's agreeableness disqualifies it as the adversarial reviewer.
- **Option Z — keep Claude + Claude (status quo):** Best per-task quality, but same-family adversarial = weaker cross-check.

**Honest challenge conclusion:** the fabrication rule makes Option X risky but intellectually the purest adversarial setup; Option Z is safest but not truly adversarial across families.

### Code blocker: no OpenAI client exists yet

`modules/llm_client.py` has clients for Anthropic, Gemini, Groq, SambaNova, DeepSeek, OpenRouter, OpenCode — but no `OpenAIClient` class and no `OPENAI_API_KEY` in `.env`. The per-step factory functions (`create_fit_client_v2`, `create_ats_client`, etc.) already support env-var routing, but only to providers that exist. To use GPT-5.6 directly:

1. Add an `OpenAIClient(LLMClient)` class (OpenAI chat-completions API)
2. Register `"openai"` in the provider map
3. Add `OPENAI_API_KEY` to `.env`
4. Set `FIT_PROVIDER=openai FIT_MODEL=gpt-5.6-luna`, `ATS_PROVIDER=openai ATS_MODEL=gpt-5.6-luna`, etc.

**Zero-code-change path:** GPT-5.6 is also reachable via OpenRouter today (`OPENROUTER_API_KEY` already in `.env`). Route fit/ATS to `openrouter/gpt-5.6-luna` immediately to trial quality vs DeepSeek without a new client class.

### Challenge verdict summary

| Claim in July 5 doc | Challenge result |
|---------------------|------------------|
| Anthropic for high-level tasks (Opus 4.8 writing, Sonnet 5 review) | Holds. Fabrication + honesty + prose quality. Fable 5 overkill. |
| GPT-5.6 "not usable, wait" | Overturned today. Sol/Terra/Luna GA July 9. |
| Sonnet 5 is the value pick (40% cheaper) | Partially overstated. Token bloat makes it pricier per task on agentic work; less impactful for single-shot calls. |
| DeepSeek/Kimi for structured tasks | Challenged by GPT-5.6 Luna/Terra — viable replacements for fit eval + ATS, now GA. |
| Opus 4.8 (writing) + Sonnet 5 (review) = good adversarial setup | Violates the project's own cross-family principle. Both Anthropic. Option X (GPT writes + Claude reviews) is the true adversarial alternative, at the cost of higher fabrication risk upstream. |

**Bottom line:** The challenge partially succeeds. Anthropic stays for the two high-level tasks (the fabrication rule is hard to override), but GPT-5.6 — available literally today — is a legitimate, arguably better replacement for the structured/analytical "other" tasks than DeepSeek/Kimi, and the only real path to true cross-family adversarial review. No code changes made this session; findings only.
