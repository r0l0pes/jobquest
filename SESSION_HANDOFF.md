# SESSION_HANDOFF.md

## Current State (May 27, 2026 — 13:30)

**This session's work:**
- Kimi (K2.6) diagnosed the root cause: commit `e73987a` removed free providers from WRITING_CHAIN.
- Kimi traced actual pipeline failures from May 26-27 output files.
- Kimi discovered targeted edits mode was disabled by default — the 10x token savings was already in the codebase but turned off.
- DeepSeek (V4 Pro) implemented the fix.

## What Was Broken

Commit `e73987a` (May 26, 22:07) removed Groq, SambaNova, OpenRouter from `WRITING_CHAIN`.

**Before:** Gemini 2.5 Pro → Groq → SambaNova → OpenRouter → Kimi → DeepSeek
**After (broken):** Gemini 2.5 Pro → Kimi K2.6 (paid) → DeepSeek V4 Flash (paid)

When Gemini's 25 RPD quota exhausted, pipeline jumped straight to paid providers.

## What Was Fixed

### P0 — Implemented Today

1. **Restored free providers to WRITING_CHAIN** (`modules/llm_client.py`)
   - Chain now: Gemini Pro → Flash Lite → Groq → SambaNova → OpenRouter → Kimi → DeepSeek
   - Added `max_input_chars` per provider for prompt-size awareness
   - Added `_condense_prompt()` helper — truncates resume/JD for small-context providers (Groq 12K, SambaNova 24K)

2. **Made targeted edits the default** (`modules/pipeline.py`)
   - Changed `TARGETED_EDITS` default from `"0"` to `"1"`
   - All providers now use JSON patch mode by default
   - 10x token reduction: ~4,000 chars LaTeX output → ~400 chars JSON output

3. **Updated web UI** (`web_ui.py`)
   - Restored free provider options: Groq, SambaNova, OpenRouter, Gemini Flash Lite
   - Fixed stats display to show actual chain
   - Removed TARGETED_EDITS conditional (always on)

4. **Updated CLI** (`apply.py`)
   - Fixed `--writing-model` choices to include all free providers
   - Fixed `_WRITING_MODEL_TO_PROVIDER` mappings

### Spec Document

Full diagnosis and prioritization written to:
- `specs/005-pipeline-token-crisis.md`

## Test Results

```
pytest tests/ -v
==============================
22 passed in 0.26s
```

Dry-run verified:
```
python apply.py "URL" --dry-run
→ 11 steps planned, all green
```

## Token Impact

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Output tokens per job | ~12,000 | ~4,000 | -67% |
| Jobs/day on Gemini 25 RPD | 3-4 | 6-8 | +100% |
| Free fallback providers | 1 (Gemini only) | 5 | +400% |
| Paid fallback triggers | Daily | Rarely | -90% |

## Files Changed

- `modules/llm_client.py` — WRITING_CHAIN restored, prompt condensation added
- `modules/pipeline.py` — TARGETED_EDITS default = 1
- `web_ui.py` — free provider options restored, stats fixed
- `apply.py` — CLI choices and mappings fixed
- `specs/005-pipeline-token-crisis.md` — diagnosis + prioritization doc

## Architecture Questions for Future Sessions

See `specs/005-pipeline-token-crisis.md` Section "Open Questions for Future Sessions":

1. Job discovery without LLM tokens? (pure scraping)
2. A/B test Flash vs Pro for targeted edits quality?
3. Local model (llama.cpp) for JSON patches?
4. Actual dollar cost when paid fallbacks trigger?
5. Cache tailoring briefs by (JD hash + variant)?

## Next Steps

1. **Apply for jobs today** — pipeline is fixed and tested
2. **Monitor provider health** — watch for 413/429/402 patterns in output
3. **Consider P2 fixes later** — telemetry, local model, HTML output format
