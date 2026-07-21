# Session Handoff — July 9, 2026

## Session Duration: ~30 min (LLM model recommendation challenge)

## What This Session Was

User challenged the top recommendation in `docs/plans/llm-model-comparison-for-pipeline.md` (dated 2026-07-05): "use Anthropic for high-level tasks." Two questions:

1. Can the latest Anthropic model still handle the high-level tasks?
2. Could GPT handle the "other" (structured/analytical) tasks instead?

Research re-run as of today, 2026-07-09. **Findings only — no code changes made.**

---

## TL;DR Verdict

- **Anthropic for high-level tasks: HOLDS.** Fabrication rule ("never fabricate resume content") + Opus 4.8's honesty/prose quality + GPT's documented metric-invention tendency make Claude the right call for Step 3 (tailoring) and Step 5 (review). Fable 5 ($10/$50, GA July 1) is overkill for 1-2 page resumes.
- **GPT for the other tasks: VIABLE, and the July 5 doc is stale here.** GPT-5.6 Sol/Terra/Luna went GA **today** (July 9). Luna ($1/$6) is a legitimate replacement for DeepSeek V4-Pro on fit eval (Step 2b) and ATS check (Step 8). Terra ($2.50/$15) is a value cut for Q&A/interview prep.
- **Cross-family adversarial gap exposed.** The July 5 chosen config (Opus writing + Sonnet review) is both-Anthropic — violates the project's own cross-family adversarial principle from the refactor plan. Option X (GPT writes + Claude reviews) is the true adversarial alternative, at the cost of higher upstream fabrication risk.

---

## What Changed Since the July 5 Doc (4 days)

| Event | Date | Impact |
|-------|------|--------|
| GPT-5.6 Sol/Terra/Luna public GA | July 9, 2026 | Overturns "wait, not usable yet" — Luna/Terra now usable for structured tasks |
| Claude Fable 5 restored to global API | July 1, 2026 | New top tier above Opus ($10/$50), but overkill for resumes |
| Sonnet 5 cost twist (Artificial Analysis) | early July | Sonnet 5 burns ~40% more output tokens + 3× agent loops → ~$2.29/task vs Opus $1.97/task on agentic work. "40% cheaper" framing overstated for agentic loads; less impactful for this pipeline's single-shot calls. |

GPT-5.6 caveat: METR flagged the highest detected-cheating rate of any public model on its Time Horizon 1.1 suite — autonomous-coding concern, not a resume-writing one.

---

## Revised Per-Step Model Table (proposed, not yet implemented)

| Step | Task | July 5 pick | July 9 challenge | Recommended |
|------|------|-------------|-------------------|-------------|
| 2b | Fit Evaluation | DeepSeek V4-Pro | GPT-5.6 Luna ($1/$6) | GPT-5.6 Luna or keep DeepSeek (both fine) |
| 3 | Tailor Resume | Claude Opus 4.8 | (challenged, holds) | **Claude Opus 4.8** (fabrication rule) |
| 5 | Adversarial Review | Claude Sonnet 5 | cross-family principle | **Claude Opus 4.8 or Sonnet 5** (see adversarial note) |
| 8 | ATS Check | DeepSeek V4-Pro | GPT-5.6 Luna | GPT-5.6 Luna or keep DeepSeek |
| 8 | Q&A + Cover | Claude Opus 4.8 | GPT-5.6 Terra | Claude Opus 4.8 if budget; Terra = value cut |
| 8b | Interview Prep | Kimi K2.6 | GPT-5.6 Terra | Keep Kimi (cheaper, templated output tolerates it) |

---

## Code Blocker (not addressed this session)

`modules/llm_client.py` has **no `OpenAIClient` class** and `.env` has **no `OPENAI_API_KEY`**. Per-step factory functions already exist and support env-var routing (`create_fit_client_v2`, `create_ats_client`, `create_reviewer_client_v2`, `create_qa_client`, `create_interview_client`), but they can only route to providers that exist in the provider map.

**To use GPT-5.6:**

- **Direct (new code):** Add `OpenAIClient(LLMClient)` class, register `"openai"` in provider map, add `OPENAI_API_KEY` to `.env`, set `FIT_PROVIDER=openai FIT_MODEL=gpt-5.6-luna` etc.
- **Zero-code path:** GPT-5.6 is reachable via OpenRouter today (`OPENROUTER_API_KEY` already in `.env`). Route to `openrouter/gpt-5.6-luna` to trial immediately without a new client class.

---

## Files Touched

| File | Change |
|------|--------|
| `docs/plans/llm-model-comparison-for-pipeline.md` | Appended "Challenge Update — 2026-07-09" section: what changed, Anthropic-holds analysis, GPT-for-other-tasks analysis, cross-family adversarial options (X/Y/Z), code blocker, verdict table |

No code changes. No tests run. No `.env` changes.

---

## Open Decisions for Next Session

1. **Trial GPT-5.6 Luna via OpenRouter** for fit eval + ATS (zero code change) — compare output quality vs DeepSeek V4-Pro on a real job run.
2. **Decide on the cross-family adversarial question:** keep same-family Claude+Claude (safe, status quo) or trial Option X (GPT writes + Claude reviews, true adversarial, higher fabrication risk upstream).
3. **If GPT trial is positive:** add `OpenAIClient` class + `OPENAI_API_KEY`, or standardize on the OpenRouter route.
4. **Sonnet 5 vs Opus 4.8 for review:** factor in the token-bloat cost finding if this pipeline ever moves to multi-loop agents (it currently uses single-shot calls, so the penalty is small).

---

## Context for the Next Agent

- Read `docs/plans/llm-model-comparison-for-pipeline.md` (the "Challenge Update — 2026-07-09" section is the current truth; the July 5 sections above it are preserved as history).
- Read `docs/plans/2026-07-05-002-refactor-scraping-llm-seams-plan.md` for the per-step client factory work that already landed (`create_tailor_client`, `create_reviewer_client_v2`, `create_ats_client`, `create_qa_client`, `create_interview_client`, `create_fit_client_v2` all exist in `modules/llm_client.py`).
- The July 5 "Session Decisions" config table in the same doc is the currently-intended setup; the July 9 challenge proposes GPT-5.6 for the structured steps but does not override it until trialed.
- `.env` keys present: `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENCODE_API_KEY`, `OPENROUTER_API_KEY`, `SAMBANOVA_API_KEY`. Missing: `OPENAI_API_KEY`.
