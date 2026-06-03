# JobQuest — Agent Guide

Pi reads this file first. It defines the project, the rules, and how to work here.

---

## What This Is

JobQuest is Rodrigo Lopes' automated job application pipeline. Paste a job URL → get a tailored PDF resume, ATS report, fit score, Q&A answers, and cover letter. Manual apply only — no auto-submission.

**Stack:** Python 3.14, Gradio 6, Playwright, Notion API, multi-provider LLM

**Test count:** 48 tests (pytest tests/ -v)

---

## Quick Start

```bash
# One-click launcher — opens Pipeline + Tracker + Discovery in 3 tabs
double-click JobQuest.command

# Or manual:
source venv/bin/activate
python serve_tracker.py --port 7880  # Tracker + Discovery + API
python web_ui.py                     # Pipeline UI on :7860
```

Then open:
- http://127.0.0.1:7860       → Pipeline (3 parallel slots)
- http://127.0.0.1:7880       → Tracker (applications)
- http://127.0.0.1:7880/queue → Discovery (job search)

```bash
# CLI
python apply.py "JOB_URL"

# Tests
pytest tests/ -v                    → 48 tests in 0.6s
```

---

## Project Structure

```
JobQuest/
├── AGENTS.md                   ← Pi reads this first
├── apply.py                    ← CLI pipeline orchestrator (--lang-resume/--lang-cover/--lang-qa)
├── web_ui.py                   ← Gradio browser UI (3 parallel slots, per-item language toggles)
├── serve_tracker.py            ← Tracker HTTP server
├── config.py                   ← Environment config
│
├── modules/
│   ├── pipeline.py             ← 10 pipeline steps + fit scoring
│   ├── llm_client.py           ← Multi-provider LLM (Gemini, Groq, SambaNova, DeepSeek, OpenRouter, Anthropic)
│   ├── scrapers/
│   │   ├── job_postings.py     ← ATS APIs + HTML scraping (6 platforms)
│   │   └── company_research.py ← Company page discovery + search
│   └── parsers.py              ← LaTeX, JSON, Q&A parsers
│
├── scripts/
│   ├── notion_reader.py        ← Read master resume from Notion
│   ├── notion_tracker.py       ← Create Notion application entries
│   ├── render_pdf.py           ← pdflatex → PDF
│   └── form_filler.py          ← Browser form filler (Playwright)
│
├── prompts/
│   ├── rodrigo-voice-lite.md   ← Writing rules (~500 tokens, DEFAULT)
│   ├── rodrigo-voice.md        ← Full writing rules (~3000 tokens, USE_FULL_VOICE=1)
│   ├── jd_analysis.md          ← Step 3a: tailoring brief
│   ├── resume_tailor.md        ← Step 3b: LaTeX generation
│   ├── tailor_review.md        ← Step 3c: compliance check
│   ├── ats_check.md            ← ATS keyword analysis
│   └── qa_generator.md         ← Q&A generation
│
├── modes/                      ← Pi agent instructions
│   ├── discover.md             ← Job discovery (search boards)
│   ├── prep_interview.md       ← Interview preparation
│   └── batch.md                ← Batch pipeline processing
│
├── data/
│   ├── job_queue.html          ← Discovery results (sortable HTML)
│   ├── job_queue.md            ← Legacy markdown queue
│   ├── tracker.html            ← Application tracker (sortable HTML)
│   └── applications.json       ← Tracker data (auto-generated)
│
├── specs/                      ← Feature specifications (9 specs)
├── tests/                      ← pytest (48 tests: 33 smoke + 11 german + 14 tracker)
├── interview-prep/             ← STAR+R story bank
├── data/
│   ├── applications.json       ← Tracker data (21 entries)
│   ├── tracker.html            ← Sortable application tracker
│   └── job_queue.html          ← Discovery results with pop-up modal
├── output/                     ← Per-application output dirs
└── templates/                  ← LaTeX resume + cover letter templates
```

---

## The Pipeline (11 Steps)

1. Scrape job posting (6 ATS APIs + HTML fallback)
2. Read master resume from Notion (cached per variant)
3. Tailor resume via LLM (3-stage: analysis → LaTeX → compliance check)
4. Write .tex file
5. Run ATS keyword coverage check
6. Review & apply ATS edits
7. Compile PDF via pdflatex
8. Generate Q&A answers (with company research)
9. Compute pipeline score (0-100)
10. _(Optional)_ Compile cover letter PDF (English or German template)
11. Save tracker entry (data/applications.json, dedup by URL)

Pipeline auto-saves: `qa`, `cover_letter_content`, `resume_content` from output dirs.

---

## Key Features (May 2026)

| Feature                    | Where                           | How                                                                 |
| -------------------------- | ------------------------------- | ------------------------------------------------------------------- |
| **Jobs Hub**               | `JobQuest.command`              | One-click launcher — Pipeline + Tracker + Discovery in 3 tabs       |
| **Job Discovery**          | `scripts/discover_jobs.py`      | Exa API search, served at `/queue` on tracker server                |
| **Discovery Pop-Up**       | `data/job_queue.html`           | Modal on load: time range (7d/24h) + keep/remove + live streaming log |
| **Live Discovery Log**     | `data/job_queue.html`, `serve_tracker.py` | Streaming stderr from discover_jobs.py shown live in modal via polling |
| **Non-blocking API**       | `serve_tracker.py`              | POST /api/discover returns job_id immediately; GET /api/discover-log for progress |
| **Cancel Discovery**       | `data/job_queue.html`           | Cancel button kills running discovery, or dismisses modal without running |
| **Fit Scoring**            | `modules/pipeline.py`           | 0-100 score from ATS, compliance, research, AI signals              |
| **Application Tracker**    | `data/tracker.html`             | Sortable HTML table, editable modals for Q&A/Cover/Resume           |
| **Tracker Fields**         | `data/applications.json`        | qa, cover_letter_content, resume_content, recompile PDF from modal  |
| **Cover Letter**           | Pipeline step 10                | LaTeX template + PDF compilation, toggled in web UI                 |
| **German Language Support** | `modules/pipeline.py`, `apply.py`, `web_ui.py` | Per-item EN/DE toggles for resume, cover letter, Q&A. CLI: `--lang-resume DE --lang-cover DE --lang-qa DE`. German section titles, T1 fontenc, "Mit freundlichen Grüßen", Du-detection for greeting. Anti-pattern injection from German Wikipedia AI-tell page. |
| **Interview Prep**         | `modes/prep_interview.md`       | Company-specific research + STAR story bank                         |
| **Batch Processing**       | `modes/batch.md`                | Queue → pipeline, sequential or parallel                            |
| **3 Resume Variants**      | Growth PM / Generalist / AI-PM  | Notion-backed, toggled in web UI                                   |
| **Voice Enforcement**      | `prompts/rodrigo-voice-lite.md` | ~500 token writing rules, injected into all writing steps            |

---

## LLM Architecture

**Writing steps (3, 6, 8):** Free-first fallback chain

```
Gemini 2.5 Pro (free, 25 RPD)
  → Gemini 3 Flash (free, 500 RPD)
    → Gemini 3.1 Flash-Lite (free, 1500 RPD)
      → Kimi K2.6 (OpenCode Go, paid)
        → DeepSeek V4 Flash (OpenRouter, paid)
          → Qwen 3.5 (OpenRouter, paid)
            → Groq Llama 3.3 70B (free)
              → SambaNova Llama 3.1 405B (free)
```

User selects primary model in web UI or via `--writing-model` CLI flag.
Fallback proceeds through the chain automatically on rate-limit errors.

**ATS check (step 5):** User-selectable + cross-provider fallback

```
User-selected (Gemini / Groq / SambaNova / OpenRouter)
  → Rate-limit → next provider in chain
```

**All free-tier providers:**

- Gemini 2.5 Pro (25 RPD), 3 Flash (500 RPD), 3.1 Flash-Lite (1500 RPD)
- Groq (1000 RPD for Llama 3.3 70B)
- SambaNova (30 RPM for Llama 3.1 405B)
- OpenRouter (200 RPD for free models)

---

## Core Rules

1. **Never fabricate resume content.** Only keywords from verified skills.
2. **Never auto-submit applications.** Rodrigo submits manually.
3. **Keep prompts honest.** Natural keyword insertion, never stuffing.
4. **Preserve verified metrics.** Numbers and scope are sacred.
5. **No em dashes anywhere.** Use commas, colons, or sentence breaks.
6. **Voice rules in `rodrigo-voice-lite.md`.** Single source of truth for writing style. German anti-patterns appended inline when `--lang-* DE`.
7. **Prompts as files.** Never inline prompt text in Python. Load from `prompts/*.md`.
8. **Test after every change.** `pytest tests/ -v` — 48 tests must pass.
9. **Spec before build.** Write spec in `specs/` before touching code.
10. **Verify with dry-run.** `python apply.py "URL" --dry-run` before marking done.
11. **Tracker data on feat/webwright-fallback branch** — that branch has application records missing from main. Always check it before declaring data lost.
12. **German output: set per-item in web UI or CLI.** Resume, cover letter, and Q&A each have independent EN/DE toggles. No auto-detect — user chooses explicitly. German section titles applied in `step_write_tex`, cover letter greetings detected via Du-usage in JD (`_use_du()`), German AI-tell block injected via `_load_voice_prefix()`.

---

## Agent Modes

Pi reads mode files from `modes/`. To use:

- **Discover jobs:** "Read `modes/discover.md` and find jobs" (now covers 12 remote-only boards)
- **Prep interview:** "Read `modes/prep_interview.md` for Company X"
- **Batch run:** "Read `modes/batch.md` and process my queue"

## Running Tests

```bash
pytest tests/ -v        # 48 tests in ~0.6s
pytest tests/ -v -k german    # Filter German language tests
pytest tests/ -v -k discover  # Filter tracker/discovery tests
pytest tests/ -v -k scoring   # Filter by name
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
| POST | `/api/discover` | Run job discovery (`{mode, clear}`) |
| GET | `/api/check-url?url=...` | Check if URL exists in tracker |

## Environment

Copy `.env.example` to `.env` and fill API keys. Required: `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `NOTION_TOKEN`, `NOTION_MASTER_RESUME_ID`.
