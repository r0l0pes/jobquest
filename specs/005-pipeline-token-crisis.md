# Pipeline Token Crisis — May 27, 2026

**Status:** Diagnosed, plan ready for implementation.
**Next step:** Implement P0+P1 fixes (40 min), then apply for jobs.

---

## What Broke

On May 26 at 22:07, commit `e73987a` removed Groq, SambaNova, and OpenRouter from the writing chain (`WRITING_CHAIN` in `modules/llm_client.py`).

**Before:** Gemini 2.5 Pro → Groq → SambaNova → OpenRouter → Kimi → DeepSeek
**After:** Gemini 2.5 Pro → Kimi K2.6 (paid) → DeepSeek V4 Flash (paid)

When Gemini exhausts its 25 RPD quota, the pipeline jumps straight to paid providers. This broke your budget constraint.

---

## How We Found It

1. Analyzed git history — traced commit `e73987a`
2. Read actual pipeline output files (`output/Aignostics_2026-05-26/` and `output/Aignostics_2026-05-27/`)
3. Found the TRUNCATED resume bug — some models omit `\section*{Experience}` header, triggering false fallback
4. Found ATS check always SKIPS with provider=Groq — prompt too large for 8K context
5. Found targeted edits mode (`TARGETED_EDITS=1`) is only enabled for Gemini Flash models — disabled for everything else

---

## The 10x Token Waste

Current default (full LaTeX generation):
- LLM outputs ~4,000 chars of LaTeX per run
- Total pipeline: ~12,000 output tokens
- At 25 RPD Gemini limit: 3-4 jobs/day

Targeted edits mode (already exists, disabled):
- LLM outputs ~400 chars of JSON patches
- Template injection applies changes to static `templates/resume.tex`
- Total pipeline: ~4,000 output tokens
- Same 25 RPD limit: 6-8 jobs/day

**The fix is already in the codebase. It's just turned off.**

---

## .tex vs .md vs .html vs .json

| Format | Token Overhead | PDF Quality | Template Injection | Verdict |
|--------|---------------|-------------|-------------------|---------|
| **LaTeX** | Baseline (~50% overhead) | Excellent | Hard (regex) | Keep for now |
| **Markdown** | **Best** (-30%) | Weak | Easy | Too simple for layout |
| **HTML** | Medium (-40%) | Excellent (CSS) | **Easy** (DOM IDs) | Best long-term |
| **JSON** | **Best** (-60%) | None | N/A | Needs renderer |

**Short-term:** Keep LaTeX, enable targeted edits (10x win).
**Long-term:** HTML output with Playwright PDF render (already a dependency). ~2-3 hour project.

---

## Prioritization (RICE)

### Must-do (P0) — Do Today

| Fix | Effort | Why |
|-----|--------|-----|
| **Enable targeted edits by default** | 5 min | 10x token reduction. Already works, just disabled. |
| **Restore free providers to WRITING_CHAIN** | 10 min | Groq, SambaNova, OpenRouter before paid fallbacks. |

### Should-do (P1) — Do Today If Time

| Fix | Effort | Why |
|-----|--------|-----|
| **Fix web UI / apply.py provider mappings** | 10 min | Dropdown shows only paid options. Stats display is wrong. |
| **Slim ATS prompt** | 15 min | ATS always SKIPS with Groq. Condense resume/JD before sending. |

### Could-do (P2) — Later

| Fix | Effort | Why |
|-----|--------|-----|
| Add provider health telemetry | 30 min | Track success/failure per provider, error types, latency. |
| Job discovery without LLM tokens | 2 hr | Pure scraping, no LLM calls for discovery. |
| Prompt caching (voice rules) | 1 hr | Reuse system prompts across steps. |
| Local model for JSON patches | 3 hr | Run 0.6B-3B model locally for targeted edits. Free forever. |

### Won't-do (P3) — Not Now

| Fix | Why |
|-----|-----|
| Switch output to HTML | 2-3 hr. Good idea but LaTeX works today. |
| TypeScript migration | 5+ hr. Nice but doesn't unblock applying. |
| Parallel execution | Complex, marginal gain. |

---

## Implementation Plan

### Step 1: modules/llm_client.py

1. Restore to `WRITING_CHAIN`:
   - `("gemini", "gemini-2.5-pro", "Gemini 2.5 Pro")`
   - `("gemini", "gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite")`
   - `("groq", "llama-3.3-70b", "Groq Llama 3.3 70B")`
   - `("sambanova", "llama-3.1-405b", "SambaNova Llama 3.1 405B")`
   - `("openrouter", "qwen/qwen3.5-397b-a17b", "OpenRouter Qwen 3.5")`
   - `("opencode", "kimi-k2.6", "Kimi K2.6")`
   - `("deepseek", "deepseek-chat", "DeepSeek V3.2")`

2. Add `max_input_tokens` awareness:
   - Estimate input size before each provider call
   - For providers with <16K context, condense master resume + JD
   - Keep system prompt intact

### Step 2: modules/pipeline.py

1. Make `TARGETED_EDITS=1` the default for ALL providers
2. Fix `_is_complete_latex` regex — some models omit `\section*{Experience}` header

### Step 3: web_ui.py + apply.py

1. Restore Groq/SambaNova/OpenRouter as writing model options
2. Fix `_WRITING_MODEL_TO_PROVIDER` mappings
3. Fix stats display string

### Step 4: Tests

Run `pytest tests/ -v` — 22 tests must pass.

---

## Open Questions for Future Sessions

1. Should job discovery use zero LLM tokens? (pure scraping)
2. Should we A/B test Flash vs Pro for targeted edits quality?
3. Should we add a local model (llama.cpp, ollama) for JSON patches?
4. What's the actual dollar cost when paid fallbacks trigger?
5. Should we cache tailoring briefs by (JD hash + variant)?

---

## Files to Reference

- `modules/llm_client.py` — WRITING_CHAIN, provider clients
- `modules/pipeline.py` — step_tailor_resume, TARGETED_EDITS logic
- `modules/parsers.py` — apply_resume_edits, template injection
- `web_ui.py` — writing model dropdown, stats display
- `apply.py` — CLI args, provider mappings
- `templates/resume.tex` — static base template for targeted edits
- `output/Aignostics_2026-05-26/` — example of working run
- `output/Aignostics_2026-05-27/` — example of broken run (TRUNCATED)
