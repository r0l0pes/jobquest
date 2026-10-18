# Handoff — JobQuest Hardening: Sendability Gate, Artifacts, Tracker Semantics, ATS Fallback

**Date:** 2026-10-03
**Branch:** `feat/pipeline-quality-gates`
**CWD:** `/Users/carvalho/Documents/VibeCoding/JQuest` (project moved from `JobSearch`)
**Status:** Factual-integrity work complete and tested (391 passed). Hardening patch NOT started.
**Audit:** read-only working-tree audit completed 2026-10-03 → `docs/audits/2026-10-03-jquest-llm-pipeline-audit.md`.

---

## 0.0 Where we are now (2026-10-03)

A read-only audit of this working tree finished. Nothing was modified by it. It verified the plan in §0/§1 below and corrected several assumptions; **read the audit before implementing anything**.

Corrections to the plan below that the audit established:

- Tracker status `"applied"` is hard-coded at **four** sites, not two: `modules/pipeline.py:1915`, `modules/pipeline.py:1943`, `apply.py:455`, `serve_tracker.py:816`.
- **`apply.py` is NOT in the working-tree diff** (at HEAD, unchanged since Jun 4). It still needs editing; do not assume local edits exist.
- `step_ats_check` uses the orchestrator's main `llm`, **not** `create_ats_client()` (`modules/pipeline.py:1257`), so `ATS_PROVIDER`/`ATS_MODEL` are currently dead for Step 5. The ATS-fallback work item must wire the factory or it will do nothing.
- A normal application makes **8 LLM calls** (9 if the Step-1 structured-extract LLM fallback fires). `TARGETED_EDITS=1` is the default, so Stage 3b is one call.
- The deterministic validators in `modules/parsers.py` already exist, are wired at three sites, and have 14 tests in `tests/test_resume_integrity.py`. The sendability gate should consume them, not replace them.
- Two unrelated bugs: `apply.py:70` CLI choice `"qwen3.5-397b-a17b"` lacks the required `qwen/` prefix; `modules/llm_client.py:435` documents Qwen pricing as `$0.15/$1.00` when live pricing is `$0.39/$2.34`.

Working-tree hazards: 45 dirty entries across two overlapping uncommitted bundles (see §3); `data/applications.json` and `data/job_queue.html` are dirty and are written by both tracker paths, so back `applications.json` up before running the suite or `apply.py`.

---

## 0. Immediate next task (not yet captured in any artifact)

Harden JobQuest for repeated real applications. Do not change resume-writing strategy or canonical content. Do not change Notion masters, portfolio, resume copy, or locked-experience rules.

### 1. Final sendability gate
After reviewer + ATS, and before/after PDF compilation, produce a deterministic status:

- `READY_TO_SEND`
- `HOLD`

`HOLD` only for:
- factual-integrity validation failure
- locked experience drift
- unsupported generated skill/claim
- LaTeX/PDF compilation or truncation failure
- missing final PDF

ATS provider failure alone is a **warning**, not a factual failure. Save `sendability_report.json` and print a concise terminal/UI summary.

### 2. Preserve application artifacts
- Do not automatically clear completed run directories.
- Each run must preserve its final `.tex`, `.pdf`, ATS report, tailoring brief, and sendability report.
- Use collision-safe run directories if necessary.

### 3. Fix tracker semantics
- A generated package is not an applied application.
- Before manual submission, tracker status must be `ready_to_apply` (or equivalent).
- Do not set `applied` automatically before the user actually submits.
- Preserve existing explicit skip/dry-run behavior.

### 4. ATS fallback
- Keep existing ATS providers.
- Add one inexpensive OpenRouter fallback for ATS analysis when free providers fail. Prefer DeepSeek V4 Flash or GLM Flash.
- If all ATS providers fail, continue with a warning and let the deterministic sendability checks run.
- Do **not** add another LLM factual-review stage.

### 5. Tests to add
- `READY_TO_SEND` clean run
- `HOLD` on factual-integrity failure
- artifacts survive completed run
- tracker uses `ready_to_apply` before submission
- ATS provider failure does not destroy an otherwise valid application package

Then run the full suite and report changed files + test result.

---

## 1. Code locations for the hardening patch (already located)

| Concern | Location |
|---|---|
| Run dir creation (date-only, NOT collision-safe) | `modules/pipeline.py::step_scrape_job()` ~L300 — `run_dir = OUTPUT_DIR / f"{company_safe}_{ts}"` |
| PDF compile (raises on failure) | `modules/pipeline.py::step_compile_pdf()` ~L1464 |
| Tracker status `"applied"` (pipeline path) | `modules/pipeline.py::step_create_tracker_entry()` — entry `:1915`, dedupe update `:1943` |
| Tracker status `"applied"` (second path) | `apply.py::_save_application_json()` `:455` — also writes `data/applications.json` |
| Tracker status `"applied"` (third path) | `serve_tracker.py:816` — discovery-queue "Move to tracker" button |
| ATS client factory | `modules/llm_client.py::create_ats_client()` ~L1065 → `FallbackClient(primary_provider="gemini")` |
| ATS check step (uses main `llm`, not `create_ats_client`) | `modules/pipeline.py::step_ats_check()` ~L1221 |
| ATS apply (grounded edits) | `modules/pipeline.py::step_apply_ats_edits()` ~L1382 → `apply_grounded_ats_edits()` |
| Provider fallback order | `modules/llm_client.py` ~L681 — `["gemini","groq","sambanova","openrouter"]` |
| Writing chain (already has OpenRouter DeepSeek V4 Flash) | `modules/llm_client.py` ~L834 — `("openrouter","deepseek/deepseek-v4-flash", ...)` |
| Factual-integrity validators | `modules/parsers.py` — `validate_resume_edits`, `validate_resume_draft`, `apply_safe_latex_replacement`, `apply_grounded_ats_edits`, `locked_experience_drift`, `extract_locked_experience_blocks` |
| Validator wiring | `modules/pipeline.py` — after Stage 3b ~L910, Step 5b ~L1065, Step 6 ~L1426/L1436 |

Note: **four** `"applied"` write sites exist (`modules/pipeline.py:1915`, `modules/pipeline.py:1943`, `apply.py:455`, `serve_tracker.py:816`). Fix all four.

---

## 2. Completed this session (verified)

### 2.1 Factual-integrity patch (JobQuest)
- `prompts/jd_analysis.md` — JD requirements absent from master stay `GAP / N/A`; no converting JD language into candidate experience; reframes must preserve source meaning.
- `prompts/resume_edits.md` — removed unsupported example skills (Agentic Workflows, Voice AI, IVR, Supabase); schema uses supported master skills only; skills limited to master inventory; metrics/attribution/scope/dates/titles immutable.
- `prompts/reviewer.md` — reviewer may not alter canonical facts, widen metric scope, or add unsupported skills; `new_string` must be escaped plain text.
- `prompts/ats_check.md` — no assumed skills without inventory evidence; localized, master-grounded edits only; unsupported keywords stay gaps.
- `modules/parsers.py` — deterministic validation + safe LaTeX escaping; `apply_resume_edits` drops invalid fields instead of applying them.
- `modules/pipeline.py` — validator after Stage 3b / 5b / 6; reviewer replacement escaped + integrity-checked; ATS switched to localized grounded edits; reviewed `.tex` persisted consistently.
- `templates/resume.tex` — canonical factual fallback: post-launch Postscript framing, canonical dates/titles, FORVIA unified-catalog attribution, C&A WhatsApp reframe, skills cleanup (no IVR/Voice AI).
- Locked experience: in `TARGETED_EDITS=1`, FORVIA HELLA / Accenture Brasil / C&A Brasil blocks must stay byte-for-byte identical through reviewer + ATS.
- `tests/test_resume_integrity.py` (new) — 14 regression tests covering the 9 Nelly failures + locked-experience protection.

### 2.2 Verification
- Nelly E2E run passed the locked-experience guard: `⊙ locked experience edit rejected (Accenture Brasil)`.
- Byte-for-byte equality confirmed for FORVIA HELLA / Accenture Brasil / C&A Brasil vs `templates/resume.tex`.
- Adversarial recruiter review verdict: **SEND**, no blockers.

### 2.3 Analysis artifacts (cross-project: `portifaria`)
- `portifaria/docs/reviews/2026-09-29-nelly-jobquest-regression-trace.md` — root-cause trace for the 9 regressions.
- `portifaria/docs/reviews/2026-09-28-postscript-resume-narrative-review.md`
- `portifaria/docs/reviews/2026-09-28-portfolio-case-study-alignment-review.md`

---

## 3. Working-tree state

Nothing committed. Two overlapping uncommitted bundles live in the same tree:

**Bundle A — Aug 2026 market refresh** (see `specs/010-august-2026-pm-market-targeting.md`):
`scripts/discover_jobs.py`, `modes/discover.md`, `data/career_config.json`, `prompts/fit_evaluation.md`, `serve_tracker.py`, `data/job_queue.html`, `tests/test_discover_jobs.py`, `tests/test_interview_prep.py`, `tests/test_salary_benchmarking.py`, `web_ui.py`, `pyrightconfig.json`, `specs/009-*`, `specs/010-*`

**Bundle B — this session (factual integrity):**
`modules/parsers.py`, `modules/pipeline.py`, `prompts/jd_analysis.md`, `prompts/resume_edits.md`, `prompts/reviewer.md`, `prompts/ats_check.md`, `templates/resume.tex`, `tests/test_resume_integrity.py`

**Shared / pre-existing (verify before discarding):**
`AGENTS.md`, `data/applications.json`, `modules/llm_client.py`, `.pi-lens/*`

Do not overwrite `data/applications.json` pre-existing edits.

---

## 4. Environment gotchas

- **`./venv/bin/pytest` shebang is broken** (points to the old `JobSearch` venv). Always use `./venv/bin/python -m pytest`.
- `apply.py` writes `data/applications.json` even with `--skip-notion` (via `_save_application_json`). Back it up before test runs and restore.
- `output/` gets cleared between sessions; do not rely on prior run dirs.
- ATS providers are flaky: Gemini `MAX_TOKENS` → Groq `404` → chain. Interview prep falls back to a basic template on OpenCode `400`. Both are non-fatal.
- `research/` is gitignored (`.gitignore:51`), so `research/market-aug-2026/*` and `research/ai_pm_context.md` are on disk but not versioned.
- `AGENTS.md` states 364 tests; actual is 391.

---

## 5. Cross-project context (do not edit from this session)

- **Notion masters updated** (Growth + Generalist): canonical dates/titles, approved Postscript narrative, orphaned-skill removal, `AI-Assisted & LLM Workflows`. Local caches rebuilt: `.master_resume_cache_2f40fd98.txt`, `.master_resume_cache_30b0fd98.txt`.
- **portifaria**: case studies aligned to the September fact register and deployed. Last production deployment `dpl_4onAo9uyQfavczgGBTQg7UkyLunM` → aliased to `rodrigolopes.xyz`.
- Regression trace lives in `portifaria`, not here.

---

## 6. Suggested skills for the next session

- **`ce-work`** — implement the hardening patch (focused, single module).
- **`tdd-red-green-refactor`** — the 5 required tests; write failing tests first.
- **`ce-code-review`** — before committing, given two overlapping uncommitted bundles.
- **`ce-commit`** — commit Bundle B (and A) once reviewed; nothing is staged.
- **`pi-subagents`** — not needed; the patch is sequential and small. Deploy only if parallelizing independent test suites.

---

## 7. Quick commands

```bash
cd /Users/carvalho/Documents/VibeCoding/JQuest
./venv/bin/python -m pytest tests/ -q          # 391 passed

# Nelly E2E (no submission)
NOTION_MASTER_RESUME_ID=2f40fd98-227b-8083-a78f-c61c38e55a12 ROLE_VARIANT=growth_pm \
  ./venv/bin/python apply.py "https://jobs.ashbyhq.com/nelly/e1974165-2055-48f1-918c-5e8cc66358e0" \
  --skip-notion --skip-form
```

**Read first:** `docs/audits/2026-10-03-jquest-llm-pipeline-audit.md` (verified baseline), then `modules/parsers.py` (validators), `modules/pipeline.py` (`step_compile_pdf`, `step_create_tracker_entry`, `step_ats_check`, `step_scrape_job`), `apply.py::_save_application_json`, `tests/test_resume_integrity.py`.
