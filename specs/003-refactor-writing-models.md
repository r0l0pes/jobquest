# PRD: Refactor Writing Pipeline LLM Selection

## Problem Statement

The writing pipeline (steps 3, 6, 8 — resume tailoring, ATS edits, Q&A generation) currently ignores the user's writing model selection from the web UI. It always falls back to OpenCode Go models regardless of what the user picked. This eats OpenCode credits unnecessarily and bypasses the free-tier providers the user configured.

Additionally, the web UI's writing model selector shows outdated models (DeepSeek V3, Gemini 2.5 Flash) that don't match the pipeline's actual behavior, and the ATS provider selector lacks OpenRouter.

## Solution

Make the writing pipeline respect the user's UI selection with a proper free-first fallback chain. The pipeline reads the `WRITING_PROVIDER` env var set by the web UI and falls back through a priority chain: free Gemini → paid OpenCode → OpenRouter → Groq.

## User Stories

1. As a user, when I select "Gemini 2.5 Pro" in the web UI, the writing steps should use Gemini 2.5 Pro, not silently switch to OpenCode Go.
2. As a user, when Gemini 2.5 Pro hits its 25 RPD limit, I want automatic fallback to Gemini 3 Flash (free), then Gemini 3.1 Flash-Lite (free), before falling to paid models.
3. As a user, I want to see all available models in the writing model selector, including free options and paid options I have API keys for.
4. As a user, I want to select "OpenRouter" as my ATS provider, alongside gemini, groq, and sambanova.
5. As a user, when I select DeepSeek V4 Flash via OpenRouter, I want the pipeline to use it directly without routing through OpenCode Go.
6. As a user, I want Kimi K2.6 to be a selectable writing model via OpenCode Go, since it's the best writing model available.
7. As a user, when I run the pipeline via CLI with a specific provider, I want that same provider chain logic to apply.
8. As a user, I want clear console output showing which model is being used for each writing step and which fallback was triggered.
9. As a user, I want the writing model selector to group models by cost (FREE vs Paid) so I can make informed choices.
10. As a user, when my selected model fails for any reason (rate limit, quota, timeout), I want the pipeline to try the next model in the chain rather than crashing.

## Implementation Decisions

### 1. Per-Task Model Mapping via WRITING_PROVIDER

The `_get_writing_client()` function in `pipeline.py` currently calls `create_writing_client(task)` which hardcodes OpenCode Go models. This will be changed to:

- Read `WRITING_PROVIDER` from env (set by web_ui.py or CLI)
- Use a task-to-model mapping that resolves the user's selected provider to the best model for that task
- If `WRITING_PROVIDER` is not set or unrecognized, default to the free-first fallback chain

### 2. Writing Fallback Chain

The fallback chain for writing steps is strictly ordered by cost and quality:

1. **Gemini 2.5 Pro** (Gemini API, free, 25 RPD) — best free writing quality
2. **Gemini 3 Flash** (Gemini API, free, 500 RPD) — excellent quality, higher quota
3. **Gemini 3.1 Flash-Lite** (Gemini API, free, 1500 RPD) — fastest, highest quota
4. **Kimi K2.6** (OpenCode Go, paid) — best overall writing quality

If the user's selected model is not in this chain (e.g., they selected DeepSeek V4 Flash), that model is tried first, then the chain proceeds from the next available slot.

### 3. ATS Provider Chain

The existing `FallbackClient` already handles provider fallback for the ATS step. OpenRouter will be added to `PROVIDER_FALLBACK_ORDER` and to the web UI's provider radio buttons.

### 4. Web UI Model Selector

The writing model radio buttons will be replaced with a dropdown that groups models by cost:

- **FREE** (Gemini API): Gemini 2.5 Pro, Gemini 3 Flash, Gemini 3.1 Flash-Lite
- **PAID** (OpenCode Go): Kimi K2.6
- **PAID** (OpenRouter): DeepSeek V4 Flash, Qwen 3.5 397B
- **FREE** (Groq): Llama 3.3 70B
- **FREE** (SambaNova): Llama 3.1 405B

The `_run_pipeline()` function in `web_ui.py` will map the user's selection to the correct `WRITING_PROVIDER` and model env vars.

### 5. Pipeline Respects UI Selection

The `create_writing_client()` factory will be updated to:

- Accept the user's selected provider/model
- Build the fallback chain starting from that selection
- Only fall through to paid models if free models are exhausted

### 6. Remove Hardcoded OpenCode Defaults

The `WRITING_TASK_MODELS` dictionary in `llm_client.py` currently hardcodes OpenCode Go models for every task. This will be replaced with a dynamic lookup based on the selected provider.

## Testing Decisions

- Test the fallback chain by mocking provider failures and verifying the next provider is called
- Test that selecting "Gemini 2.5 Pro" in the UI results in Gemini 2.5 Pro being used
- Test that rate limit errors trigger fallback without crashing
- Test that unknown provider selections default to the free-first chain
- The existing `tests/test_smoke.py` already tests provider registration and pipeline step presence — these will be extended to cover the new writing provider logic

## Out of Scope

- Changing the LLM prompt templates or voice rules
- Adding new pipeline steps
- Changing the ATS check logic (only the provider selection)
- Adding real-time model availability checking (assumes models listed are available)
- Cost tracking or billing integration

## Prompt Architecture Decisions

### JD Analysis Brief (`prompts/jd_analysis.md`)

**Problem:** The current 300+ line brief produces prescriptive keyword maps ("insert X into bullet Y") that the resume tailor treats as requirements. This causes keyword stuffing.

**Solution:** Rewrite as a short XML-structured brief (~50 lines) with few-shot examples.

```xml
<brief>
  <role_diagnosis>What problem is this company solving?</role_diagnosis>
  <themes>3 themes the role values, in the company's own language</themes>
  <candidate_matches>Where Rodrigo's work maps to each theme, quoted from resume</candidate_matches>
  <do_not_change>Bullets already strong — leave as-is</do_not_change>
</brief>
```

No more "insert X into bullet Y" instructions. Themes only.

### Resume Tailor (`prompts/resume_tailor.md`)

**Problem:** The abstract rule "JD exact language where accurate" produced "grit" in a WFP bullet — the model doesn't understand the boundary between "accurate" and "reframing."

**Solution:** Replace the rule with 3 few-shot boundary examples showing:

- Good: JD says "B2C2B" → resume says "individual users + organisational adoption" → reframe to make pattern obvious without forcing acronym
- Bad: JD says "grit" → resume says "validated 60% cost efficiency" → do NOT add "grit" — reframes the work entirely
- Good: JD says "Sales and Customer Success" → resume says "commercial teams" → swap because accurate

### Summary Rule

**Problem:** Current rule says "name 3 things the company cares about" — produced "0 to 1, self-serve UX, marketing teams" (all JD words, none from master resume).

**Solution:** New success criteria — "Name 2 things Rodrigo has built that this company specifically needs, using his language. Then name 1 company challenge he has solved before. No more than 3 sentences. Every claim must be backed by an Experience bullet."

Example for Contentful:

> "8 years scaling B2B self-serve platforms (HELLO 60K workshops, €12M revenue) and PLG checkout flows (C&A 28% CVR, Natura 45% CVR). Built AI products from validation to scaling for 20+ country programs (WFP). Now applying that to making technical platforms accessible to non-technical users."

### Voice Rules (`prompts/rodrigo-voice-lite.md`)

**Addition:** "grit" added to banned words — it's a generic buzzword that appeared in LLM output and is not in Rodrigo's natural vocabulary.
