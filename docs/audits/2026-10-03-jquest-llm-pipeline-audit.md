# JQuest LLM Pipeline Audit — Read-Only Working-Tree Review

**Date:** 2026-10-03
**Branch:** `feat/pipeline-quality-gates`
**Scope:** current local working tree only
**Method:** read-only. No existing file was modified, formatted, installed, committed, stashed, reset, or deleted. This document is the only file created by the audit.

---

## 1. Git state

| Check | Result |
| --- | --- |
| `git status --short --branch` | `## feat/pipeline-quality-gates...origin/feat/pipeline-quality-gates` — branch tracks remote, no ahead/behind marker |
| HEAD | `4f9c1241db970a06e44f234add69ce1a954840bd` |
| HEAD subject | `feat: per-step model assignment analysis for adversarial trial` |
| Ahead/behind remote | `0  0` (HEAD == `origin/feat/pipeline-quality-gates`) |
| **Working tree differs from remote?** | **YES — 45 dirty entries, all uncommitted.** No commits diverge; the entire delta is local working-tree changes. |

Dirty substance (excluding `.pi-lens/` telemetry):

- **Modified:** `AGENTS.md`, `SESSION_HANDOFF.md`, `modules/llm_client.py` (+182), `modules/pipeline.py`, `modules/parsers.py`, `web_ui.py`, `serve_tracker.py`, `scripts/discover_jobs.py`, `templates/resume.tex`, `prompts/{ats_check,fit_evaluation,jd_analysis,resume_edits,reviewer}.md`, `tests/{test_discover_jobs,test_fit_evaluation,test_interview_prep,test_salary_benchmarking}.py`, `data/applications.json`, `data/career_config.json`, `data/job_queue.html`
- **Untracked:** `specs/009-second-laptop-portability.md`, `specs/010-august-2026-pm-market-targeting.md`, `tests/test_resume_integrity.py`, `pyrightconfig.json`, `.pi-lens/recent-touches.json`, `node_modules/`
- **`apply.py` is NOT in the diff** (last touched Jun 4, at HEAD) despite the handoff claiming it needs the tracker-status fix.

Test count: **391** `def test_` functions. (AGENTS.md says 377; SESSION_HANDOFF says 391.)

---

## 2. Exact LLM call table

`—` = unset, defaults apply. "Required/optional" = whether a failure aborts the whole run.

| # | Stage (step) | Function (file:line) | Client factory | Provider | Model slug sent | Env var(s) | Fallback behavior | Req/Opt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | S1 scrape → enrich | `StructuredExtractor.enrich` → `_extract_via_llm` (`structured_extractor.py:77,166`) | `create_ats_client()` (`llm_client.py:1065`) | gemini | `models/gemini-3.1-flash-lite` | `ATS_PROVIDER`/`ATS_MODEL` (—), `FIRECRAWL_API_KEY` | Firecrawl `/extract` first, else LLM; then `FallbackClient` gemini→groq→sambanova→openrouter; all failures swallowed (`pass`) | **Optional** (conditional: only if Firecrawl absent/fails and desc ≥ 100 chars) |
| 2 | S2b fit gate | `step_evaluate_fit` (`pipeline.py:546-549`) | `create_fit_client_v2()` (`llm_client.py:1118`) | gemini | `models/gemini-3.1-flash-lite` | `FIT_PROVIDER`/`FIT_MODEL` (—) | `create_client(provider="gemini", model="gemini-3.1-flash-lite", fallback=False)` → Gemini-internal `MODEL_FALLBACK_ORDER` on 429/truncation; on final failure gate is **skipped**, score forced to 50 / `UNKNOWN (eval failed)` | **Optional** for the LLM, but its result can **block** the run (`FitGateBlocked`) |
| 3 | S3a JD analysis | `step_tailor_resume` (`pipeline.py:789`) | `create_tailor_client()` (`llm_client.py:1032`) | gemini (chain head) | `models/gemini-2.5-pro` | `TAILOR_PROVIDER`/`TAILOR_MODEL` (—) → `WRITING_PROVIDER`/`WRITING_MODEL`/`GEMINI_WRITING_MODEL` (—) | `_WritingFallbackClient` walks full `WRITING_CHAIN` (9 entries) on any exception | **Required** (no try/except) |
| 4 | S3b LaTeX / JSON patch | same, `pipeline.py:817` (targeted, default) or `:895` (full) | `create_tailor_client()` | gemini | `models/gemini-2.5-pro` | same | chain + `content_validator=_is_complete_latex` (full mode only) | **Required** |
| 5 | S3c brief compliance | same, `pipeline.py:932` | `create_tailor_client()` — **same client, no dedicated factory** | gemini | `models/gemini-2.5-pro` | same | chain inside client; outer `try/except` → "skipped" | **Optional** |
| 6 | S5 adversarial reviewer | `step_review_drafts` (`pipeline.py:987,1021`) | `create_reviewer_client_v2()` (`llm_client.py:1048`) | gemini | `models/gemini-3.1-flash-lite` | `REVIEWER_PROVIDER`/`REVIEWER_MODEL` (—) | `create_reviewer_client()` → `FallbackClient(gemini)` → gemini→groq→sambanova→openrouter; outer `try/except` → `review_feedback=None` | **Optional** |
| 7 | S5 ATS check | `step_ats_check` (`pipeline.py:1221,1257`) | **main orchestrator `llm`** (`apply.py:351 create_client(provider, fallback=True)`) — **not** `create_ats_client()` | gemini (default) | `models/gemini-3.1-flash-lite` | `LLM_PROVIDER` or `--provider`; **`ATS_PROVIDER`/`ATS_MODEL` ignored here** | `FallbackClient` gemini→groq→sambanova→openrouter; outer `try/except` → synthetic `SKIPPED` report @ 50% | **Optional** |
| 8 | S8 Q&A (+ cover-letter body) | `step_generate_qa` (`pipeline.py:1561,1608`) | `create_qa_client()` (`llm_client.py:1081`) | gemini (chain head) | `models/gemini-2.5-pro` | `QA_PROVIDER`/`QA_MODEL` (—) → writing chain | `_WritingFallbackClient` full chain | **Required** (no try/except) |
| 9 | S8b interview prep | `step_generate_interview_prep` (`pipeline.py:1678,1726`) | `create_interview_client()` (`llm_client.py:1097`) | opencode | `kimi-k2.6` | `INTERVIEW_PROVIDER`/`INTERVIEW_MODEL` (—) | opencode → (on `ValueError`/absent key) writing chain; outer `try/except` → `_fallback_interview_prep()` template | **Optional** |

**Non-LLM (deterministic) steps:** S2 read master resume (Notion), S4 write `.tex`, S5b apply reviewer feedback (exact-string replace + validators), S6 ATS edits (`apply_grounded_ats_edits`), S7 compile PDF (`compile_and_inspect`, raises → **Required**), S9 cover-letter compile (reuses Q&A answer), S9 score, S9 tracker, S10 form filler. `research_company` (S8) is HTTP/Firecrawl — no LLM.

### One normal application = 8 LLM calls (9 if the Step-1 structured-extract fallback fires)

3a, 3b, 3c, reviewer, ATS, QA, interview, fit = 8. Default `TARGETED_EDITS=1` (set explicitly by `web_ui.py:180`) means 3b is 1 call, not 2. Retries/fallbacks add calls on failure.

---

## 3. Specific verification

| Question | Finding |
| --- | --- |
| **Does `deepseek-chat` still exist?** | **YES.** `DeepSeekClient.DEFAULT_MODEL = "deepseek-chat"` (`llm_client.py:359`); last entry of `WRITING_CHAIN` (`:839`); in `apply.py:73` `--writing-model` choices; in `web_ui.py:163` as "DeepSeek V3.2 (paid)". |
| **Exact OpenRouter model(s)** | Exactly two slugs: `deepseek/deepseek-v4-flash` (`WRITING_CHAIN:834`) and `qwen/qwen3.5-397b-a17b` (`WRITING_CHAIN:835`; also `OpenRouterClient.DEFAULT_MODEL`, `:438`). Both confirmed live on OpenRouter. **Slug bug:** `apply.py:70` CLI choice is `"qwen3.5-397b-a17b"` (no `qwen/` prefix) mapping to provider `openrouter` → would send a bare slug. `web_ui.py` uses the correct prefixed slug. |
| **JSON Schema structured outputs?** | **NO — markdown/regex parsing throughout.** `llm_client.py` never sets `response_schema` / `response_mime_type` / `response_format`. Parsing lives in `parsers.py`: `parse_ats_report` (```` ```json ```` fence + `# ATS Check` header), `parse_qa_answers` (3 regex strategies), `parse_resume_edits` (`json.loads` on fence-stripped text), `_parse_review_feedback` (JSON fence for Part A, `SUGGESTION:` line-scan for Part B), `_parse_fit_evaluation`, `_safe_parse_json` (trailing-comma fixup). The only real JSON Schema is Firecrawl's `extraction_schema` (`structured_extractor.py:118`) — server-side, not an LLM-provider structured output. |
| **Fit and JD analysis separate calls?** | **YES, two separate calls, two different models.** `step_evaluate_fit` (`fit_evaluation.md`, gemini-3.1-flash-lite, temp 0.2) vs `step_tailor_resume` Stage 3a (`jd_analysis.md`, gemini-2.5-pro, temp 0.2). Different prompts, different clients, different run-dir artifacts. |
| **Reviewer/ATS edits trigger an extra LLM rewrite?** | **NO.** `step_apply_review` is deterministic string replacement + `validate_resume_draft` + `locked_experience_drift`; `step_apply_ats_edits` calls `apply_grounded_ats_edits` (deterministic, exact-match only). Zero extra LLM calls. |
| **Provider vs model fallback semantics** | Two independent layers. (a) **Provider fallback** — `PROVIDER_FALLBACK_ORDER = ["gemini","groq","sambanova","openrouter"]` (`:681`); `FallbackClient` advances only on `is_transient` errors (429/rate/quota/exhausted/limit/timeout/network/5xx); auth/config errors `raise` immediately. (b) **Model fallback** — `MODEL_FALLBACK_ORDER` (`:31`) inside `GeminiClient` only, plus `_WritingFallbackClient` (chain of `(client, max_input_chars)`) which falls through on **any** exception and on validator failure. `openrouter` is in the provider chain; `openai`/`anthropic`/`opencode`/`deepseek` are **not**. |
| **Do optional-stage failures abort the run?** | **Mixed.** Guarded (non-fatal): fit, 3c compliance, reviewer, ATS, interview prep, structured extract. **Unguarded (abort):** `step_generate_qa` (`:1608`, bare `writing_llm.generate`), `step_compile_pdf` (`raise RuntimeError`), `step_read_master_resume` (`raise RuntimeError` on short content), `step_scrape_job`, `step_write_tex`. The orchestrator loop (`apply.py:395-405`) converts any uncaught exception into `return 1` after `_save_context` — so reviewer/ATS/interview cannot abort, but **Q&A can**. |
| **Artifact directory naming/persistence** | `OUTPUT_DIR / f"{company_safe}_{ts}"` with `ts = date.today().isoformat()` (`pipeline.py:300-304`). **Date-granular, not unique.** A second run for the same company on the same day reuses (overwrites) the directory, including resume PDF, ATS report, tailoring brief. No `rmtree`/`shutil` anywhere in the repo, so runs are never auto-cleared by code (`output/` currently holds only 3 stale `TestCorp_2026-06-04`-style dirs, each with one leftover file). |
| **Tracker default status** | **`"applied"` — both write paths, no exceptions.** `pipeline.py:1915` (new entry) and `:1943` (dedup update); `apply.py:455` (`_save_application_json`). `serve_tracker.py:816` also writes `status: "applied"` from the discovery queue's "Move to tracker" button. `data/tracker.html:560-565` offers `applied, screening, interview, offer, rejected` — no `ready_to_apply`/`generated`. |
| **Can package generation mark a job Applied?** | **YES — it always does.** Every successful pipeline run writes `"status": "applied"` before the user has submitted anything, and `apply.py` does so *even with* `--skip-notion` (handoff §4 confirms). |
| **Does a deterministic READY_TO_SEND/HOLD gate exist?** | **NO.** Grep across `.py`/`.md`/`.json`/`.html` finds `READY_TO_SEND` only in `SESSION_HANDOFF.md:17` — an **unimplemented proposal**. No `sendability_report.json`, no `HOLD`, no sendability function. Deterministic validators that would feed it do exist: `validate_resume_edits`, `validate_resume_draft`, `locked_experience_drift`, `apply_safe_latex_replacement`, `apply_grounded_ats_edits` (`parsers.py:357-503`), wired at `pipeline.py:910`, `:1065`, `:1436`; 14 tests in `tests/test_resume_integrity.py`. |

---

## 4. Verdict on the proposed changes

| Proposed change | Verdict | Evidence |
| --- | --- | --- |
| Merge fit + JD analysis | **CONFIRMED** | Premise holds: two separate calls, two models, two prompts (`pipeline.py:546` vs `:789`). Nothing merges them today. |
| Keep one adversarial reviewer | **CONFIRMED (with caveat)** | Exactly one adversarial reviewer exists (`step_review_drafts`); but a *second* LLM review pass, `3c` brief compliance (`:932`), shares the drafter's client — the natural merge target. |
| Deterministic integrity validation | **CONFIRMED (already exists)** | `validate_resume_draft` / `validate_resume_edits` / `locked_experience_drift` are deterministic, wired at 3 sites, with a 14-test suite. "Add it" = extend/harden, not build. |
| Deterministic ATS exact match | **CONFIRMED (already exists)** | `apply_grounded_ats_edits` (`parsers.py:470`) applies only exact-match, master-grounded, integrity-checked edits; unsupported edits are skipped, never LLM-rewritten. |
| One cheap semantic ATS call | **CONTRADICTED as stated** | There is exactly **one** ATS LLM call today (`step_ats_check`), already on a cheap model (gemini-3.1-flash-lite) — but it does **not** use `create_ats_client()`; it uses the orchestrator's main `llm`. The real gap is factory wiring plus the missing OpenRouter ATS fallback (handoff §4), not call count. |
| Deterministic patch application | **CONFIRMED (already exists)** | `apply_safe_latex_replacement` + `apply_resume_edits` + `apply_grounded_ats_edits` are all deterministic and integrity-gated. |
| Optional interview prep | **CONFIRMED** | `step_generate_interview_prep` is an unconditional entry in `build_steps()` (`apply.py:141`); no `--skip-interview` flag. Its *failure* is already non-fatal (template fallback), but its *execution* is mandatory. |
| Generated→Ready to Apply→Applied lifecycle | **CONTRADICTED** | Code hard-codes `"applied"` at four sites (`pipeline.py:1915`, `:1943`, `apply.py:455`, `serve_tracker.py:816`). No `ready_to_apply` state exists in code or in `tracker.html` `STATUS_OPTIONS`. |
| Unique run directories | **CONTRADICTED** | `f"{company_safe}_{date.today().isoformat()}"` is collision-prone within a day, and `mkdir(exist_ok=True)` silently reuses. |
| Deterministic sendability gate | **CONTRADICTED (does not exist)** | Only the handoff proposal mentions it. No `sendability_report.json`, no READY_TO_SEND/HOLD logic. |

---

## 5. Cost per application

**Token usage is NOT logged.** `llm_client.py` never reads `response.usage` / `usage_metadata` / `prompt_tokens`; nothing writes token counts anywhere. `.usage_stats.json` (dated 2026-07-05) stores only *call counts* per provider, and `web_ui.py:239-248` synthesizes them with a `4 // (n+1)` heuristic — it is not a measurement. The estimate below therefore uses **explicit token assumptions**.

### Token assumptions (char/4 ≈ tokens; prompt sizes measured from `prompts/*.md` plus pipeline slices)

| Stage | Input tok | Output tok |
| --- | --- | --- |
| S1 structured extract (conditional) | 0.9K | 0.15K |
| S2b fit | 7.6K | 0.35K |
| S3a JD analysis | 4.5K | 0.6K |
| S3b targeted edits | 4.9K | 0.5K |
| S3c compliance | 3.8K | 0.25K |
| S5 reviewer | 9.0K | 1.2K |
| S5 ATS | 6.6K | 1.5K |
| S8 Q&A | 11.0K | 2.5K |
| S8b interview | 7.0K | 2.0K |
| **Total (9 calls)** | **≈ 55K** | **≈ 9K** |
| **Total (8 calls, no S1 LLM)** | **≈ 54K** | **≈ 8.9K** |
| Planning range incl. retries/contingency | **50–80K** | **8–15K** |

**Actual slugs on the default path:** `gemini-2.5-pro` ×4 (3a/3b/3c/QA), `gemini-3.1-flash-lite` ×3 (fit, reviewer, ATS) + ×1 conditional (S1), `kimi-k2.6` (opencode) ×1.

### Cost

| Scenario | Cost / application |
| --- | --- |
| **Default (Gemini free tier + OpenCode flat-rate)** | **$0.00 marginal.** Binding constraint is quota, not money: Gemini 2.5 Pro free tier ≈ 25 RPD ÷ 4 Pro calls/app ≈ **6 applications/day ceiling**; Flash-Lite ~1500 RPD is not a constraint. |
| All calls on `qwen/qwen3.5-397b-a17b` (OpenRouter, verified $0.39/M in · $2.34/M out) | 55K×0.39e-6 + 9K×2.34e-6 ≈ $0.021 + $0.021 = **$0.043** (range $0.04–0.06) |
| All calls on `deepseek/deepseek-v4-flash` (OpenRouter; DeepSeek first-party $0.15/M in · $0.60/M out) | 55K×0.15e-6 + 9K×0.60e-6 ≈ $0.008 + $0.005 = **$0.014** (OpenRouter weighted average is lower; DeepSeek's own rate is the conservative upper bound ≈ $0.014–0.03) |
| All calls on `deepseek-chat` (DeepSeek direct, $0.28/M in cold · $0.42/M out, $0.028/M cached — pricing not in repo, assumed) | ≈ **$0.019** cold; materially lower with prefix caching on the static prompt prefixes (`qa_generator`, `fit_evaluation`) |

> **Stale pricing in code:** `llm_client.py:435` documents Qwen as "$0.15/$1.00 per 1M". Live OpenRouter is $0.39/$2.34 — under-estimated by ~2.6×/2.3×. Any cost model built from that docstring will under-estimate by roughly half.

**Largest cost/quality levers by token share:** reviewer (16% of input), Q&A (20%), fit (14%) — the fit call alone ships a 4.9K-token system prompt for a ~350-token classification output.

---

## 6. Notable findings not asked for

1. **`ATS_PROVIDER`/`ATS_MODEL` are dead config for the ATS step.** `create_ats_client()` exists, is unit-tested, and is called only from `structured_extractor._extract_via_llm`. `step_ats_check` uses the orchestrator's main `llm` (`pipeline.py:1257`). Setting `ATS_MODEL` today changes Step 1 enrichment, not Step 5.
2. **`apply.py` is not in the working-tree diff** despite `SESSION_HANDOFF.md` claiming it needs the tracker-status fix — it is at HEAD, unchanged, and still writes `"applied"` at line 455.
3. **Two tracker write paths** both fire on a normal run: `step_create_tracker_entry` (unless `--skip-notion`) *and* `_save_application_json`. `data/applications.json` is edited by both.
4. **`data/applications.json` and `data/job_queue.html` are dirty.** Running the suite (which the handoff warns writes `applications.json`) would mutate tracked data. The suite was **not** run during this audit.
5. **Deprecated factories are still what the tests mock.** `_get_writing_client`, `_get_fit_client`, `_get_reviewer_client` (`pipeline.py:71-136`) are patched by `tests/test_behavioral_profile.py`, `test_reviewer.py`, and `test_fit_evaluation.py`, while production uses the v2 factories — the tests exercise a path production no longer takes.
