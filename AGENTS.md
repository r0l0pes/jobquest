# JobQuest — Agent Guide

Pi reads this file first. It defines the project, the rules, and how to work here.

---

## What This Is

JobQuest is Rodrigo Lopes' automated job application pipeline. Paste a job URL → get a tailored PDF resume, ATS report, fit score, Q&A answers, and cover letter. Manual apply only — no auto-submission.

**Stack:** Python 3.14, Gradio 6, Playwright, Notion API, multi-provider LLM

**Test count:** 186 tests (pytest tests/ -v)

---

## Quick Start

```bash
double-click JobQuest.command                    # Launcher (3 tabs)
source venv/bin/activate
python apply.py "JOB_URL"                         # Run full pipeline
python apply.py "JOB_URL" --skip-reviewer          # Skip adversarial review
python apply.py --upskill                          # Skill gap analysis
pytest tests/ -v                                   # 186 tests
```

---

## Project Structure

| Directory | Purpose |
|-----------|---------|
| `modules/` | Pipeline orchestration, LLM clients, scrapers, parsers, upskill analysis |
| `scripts/` | Notion I/O, PDF compile, form filler, salary lookup, **discovery** |
| `prompts/` | LLM prompt templates (writing rules, fit eval, reviewer, behavioral profile) |
| `modes/` | Pi agent instructions (discover, prep_interview, batch, upskill) |
| `data/` | Queue HTML, tracker HTML, applications JSON, templates |
| `tests/` | pytest suite (186 tests) |

---

## The Pipeline (15 Steps)

1. Scrape job posting (6 ATS APIs + HTML fallback)
2. Read master resume from Notion (cached per variant)
3. **Fit Evaluation Gate** — score job fit (0-100) before spending tokens
4. Tailor resume via LLM (3-stage: analysis → LaTeX → compliance check)
5. Write .tex file
6. **Adversarial review** — separate LLM call critiques drafts for fabrications, missed keywords, tone mismatches
7. **Apply reviewer feedback** — JSON patch edits to .tex, narrative suggestions logged
8. Run ATS keyword coverage check
9. Review & apply ATS edits
10. **Compile PDF** (compile-and-inspect loop — auto-fix orphan entries, page spills, isolated sections)
11. Generate Q&A answers (with company research + salary benchmark context)
12. Generate interview prep (STAR examples, likely questions, company talking points)
13. Compute pipeline score (0-100)
14. _(Optional)_ Compile cover letter PDF
15. Save tracker entry (`data/applications.json`, dedup by URL)

---

## LLM Architecture

Free-first fallback chain defined in `modules/llm_client.py`. User selects primary model via `--writing-model` flag or web UI; fallback proceeds automatically on rate-limit errors. See `modules/llm_client.py` for current provider chain and rate limits.

---

## Core Rules

1. **Never fabricate resume content.** Only keywords from verified skills (reviewer step checks this).
2. **Never auto-submit applications.** Rodrigo submits manually.
3. **Keep prompts honest.** Natural keyword insertion, never stuffing.
4. **Preserve verified metrics.** Numbers and scope are sacred.
5. **No em dashes.** Use commas, colons, or sentence breaks.
6. **Voice rules in `rodrigo-voice-lite.md`.** Single source of truth for writing style.
7. **Prompts as files.** Never inline prompt text — load from `prompts/*.md`.
8. **Test after every change.** `pytest tests/ -v` — 186+ tests must pass.
9. **Spec before build.** Write spec in `specs/` before touching code.
10. **Verify with dry-run.** `python apply.py "URL" --dry-run` before marking done.
11. **Tracker data on feat/webwright-fallback branch** — check for application records missing from main.

---

## Agent Modes

Pi reads mode files from `modes/`. To use:

- **Discover jobs:** "Read `modes/discover.md` and find jobs" (now covers 12 remote-only boards)
- **Prep interview:** "Read `modes/prep_interview.md` for Company X"
- **Batch run:** "Read `modes/batch.md` and process my queue"

## Running Tests

```bash
pytest tests/ -v        # 186 tests in ~1.4s
pytest tests/ -v -k reviewer  # Filter reviewer tests
pytest tests/ -v -k salary    # Filter salary benchmarking tests
pytest tests/ -v -k upskill   # Filter upskill gap analysis tests
pytest tests/ -v -k behavior  # Filter behavioral profile tests
```

## Tracker Server API

The tracker server (`serve_tracker.py`) exposes these endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Tracker page |
| GET | `/queue` | Discovery page |
| GET | `/api/applications` | List all applications |
| POST | `/api/applications` | Save all applications (full replace) |
| POST | `/api/recompile` | Rewrite .tex + regenerate PDF |
| POST | `/api/discover` | Start job discovery (async — returns immediately, poll `/api/discover/status` for completion) |
| GET | `/api/discover/status` | Poll discovery progress: `{running, jobs_found, error}` |
| GET | `/api/check-url?url=...` | Check if URL exists in tracker |

## Environment

Copy `.env.example` to `.env` and fill API keys. Required: `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `NOTION_TOKEN`, `NOTION_MASTER_RESUME_ID`.
