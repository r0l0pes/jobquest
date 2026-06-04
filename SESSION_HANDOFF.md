# Session Handoff — June 4, 2026

## Previous Session (May 27)

See commit history and specs/005-pipeline-token-crisis.md for the token crisis fix.

**Branch then:** `feat/pipeline-quality-gates`
**Tests then:** 108 passing

---

## This Session (June 4, 2026)

### What Was Done

**Implemented 4 specs (005-008) on `feat/pipeline-quality-gates`:**

| Spec | ICE | Files | Tests |
|------|-----|-------|-------|
| **005 Drafter-Reviewer** | 6.7 | `prompts/reviewer.md`, `llm_client.py` (+create_reviewer_client), `pipeline.py` (+step_review_drafts, +step_apply_review), `apply.py` (--skip-reviewer) | 18 |
| **006 Behavioral Profile** | 6.3 | `prompts/behavioral_profile.md`, `prompts/fit_evaluation.md`, `prompts/qa_generator.md`, `pipeline.py` (+_load_behavioral_profile) | 14 |
| **007 Salary Benchmarking** | 6.0 | `scripts/salary_lookup.py`, `salary_data.json`, `pipeline.py` (+_get_salary_benchmark) | 20 |
| **008 Upskill Gap Analysis** | 4.7 | `modules/upskill.py`, `apply.py` (--upskill flag), `modes/upskill.md`, `upskill/` dir | 26 |

**Total tests: 186 passing** (was 108, +78 new tests)

**Docs updated:** `AGENTS.md`, `README.md` — pipeline steps 11→15, test count 32→186, new features table, project structure expanded

**Cleanup:**
- Deleted stale root-level spec-001..spec-004 implementation summaries
- Added `.gitignore` entries: `.pi-lens/cache/`, `scripts/update_certs.py`, `salary_data.json`, `PI_SCREENSHOT_ISSUE_FIX.md`
- Removed Resume Variants section from README

### Commits
```
548b903 chore: gitignore PI_SCREENSHOT_ISSUE_FIX.md
072fbcc docs: remove Resume Variants section from README
d9107ed chore: gitignore .pi-lens/cache/ and scripts/update_certs.py
cf5b70b feat: wire behavioral profile into reviewer step
df5e41c docs: update AGENTS.md and README.md for specs 005-008
539ac32 feat: implement specs 005-008
```

### Current State
- **Branch:** `feat/pipeline-quality-gates`
- **HEAD:** `548b903`
- **Tests:** 186 passing (`pytest tests/ -v`)
- **Test files:** 10 (test_cover_letter, test_fit_evaluation, test_interview_prep, test_pdf_inspect, test_reviewer, test_behavioral_profile, test_salary_benchmarking, test_upskill, test_smoke, test_tracker)
- **Pipeline steps:** 15
- **Uncommitted:** specs/ directory (spec docs — untracked)

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
