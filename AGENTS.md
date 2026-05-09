# JobQuest — Agent Guide

Pi reads this file first. It defines the project, the rules, and how to work here.

---

## What This Is

JobQuest is Rodrigo Lopes' automated job application pipeline. Paste a job URL → get a tailored PDF resume, ATS report, fit score, and application answers. Manual apply only — no auto-submission.

**Stack:** Python 3.14, Gradio 6, Playwright, Notion API, multi-provider LLM

---

## Quick Start

```bash
source venv/bin/activate

# Web UI (3 parallel slots)
python web_ui.py                    → http://127.0.0.1:7860

# CLI
python apply.py "JOB_URL"
python apply.py "JOB_URL" --fill-form

# Tracker
python serve_tracker.py             → http://127.0.0.1:7878

# Tests
pytest tests/ -v                    → 22 tests in 0.2s
```

---

## Project Structure

```
JobQuest/
├── AGENTS.md                   ← Pi reads this first
├── apply.py                    ← CLI pipeline orchestrator
├── web_ui.py                   ← Gradio browser UI (3 parallel slots)
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
├── specs/                      ← Feature specifications
├── tests/                      ← pytest smoke tests
├── interview-prep/             ← STAR+R story bank
└── templates/                  ← LaTeX resume template
```

---

## The Pipeline (10 Steps + Optional)

1. Scrape job posting (6 ATS APIs + HTML fallback)
2. Read master resume from Notion (cached per variant)
3. Tailor resume via LLM (3-stage: analysis → LaTeX → compliance check)
4. Write .tex file
5. Run ATS keyword coverage check
6. Review & apply ATS edits
7. Compile PDF via pdflatex
8. Generate Q&A answers (with company research)
9. **Compute pipeline score (0-100)** — NEW
10. Create Notion tracker entry
11. *(Optional)* Open form filler (`--fill-form`)

---

## Key Features (May 2026)

| Feature | Where | How |
|---|---|---|
| **Job Discovery** | `modes/discover.md` | Pi searches boards, outputs to `data/job_queue.html` |
| **Fit Scoring** | `modules/pipeline.py` | 0-100 score from ATS, compliance, research, AI signals |
| **Application Tracker** | `data/tracker.html` | Sortable HTML table, `python serve_tracker.py` |
| **Interview Prep** | `modes/prep_interview.md` | Company-specific research + story bank |
| **Batch Processing** | `modes/batch.md` | Queue → pipeline, sequential or parallel |
| **3 Resume Variants** | Growth PM / Generalist / AI-PM | Notion-backed, toggled in web UI |
| **Voice Enforcement** | `prompts/rodrigo-voice-lite.md` | ~500 token writing rules, injected into all writing steps |

---

## LLM Architecture

**Writing steps (3, 6, 8):** Quality-first chain
```
Gemini 3 Flash (free, 500 RPD)
  → DeepSeek V3.2 (~$0.005/app)
    → OpenRouter / Qwen3.5-397B
      → Groq → SambaNova
```

**ATS check (step 5):** Free-tier providers
```
User-selected (Gemini / Groq / SambaNova)
  → Rate-limit → next model → next provider
```

**Free-tier Gemini models (verified May 2026):**
- Gemini 3 Flash (500 RPD) — default
- Gemini 3.1 Flash-Lite (stable, cheapest)
- Gemini 2.5 Pro (25 RPD, most capable)
- Gemini 2.5 Flash (500 RPD)
- Gemini 2.5 Flash-Lite (1500 RPD)

---

## Core Rules

1. **Never fabricate resume content.** Only keywords from verified skills.
2. **Never auto-submit applications.** Rodrigo submits manually.
3. **Keep prompts honest.** Natural keyword insertion, never stuffing.
4. **Preserve verified metrics.** Numbers and scope are sacred.
5. **No em dashes anywhere.** Use commas, colons, or sentence breaks.
6. **Voice rules in `rodrigo-voice-lite.md`.** Single source of truth for writing style.
7. **Prompts as files.** Never inline prompt text in Python. Load from `prompts/*.md`.
8. **Test after every change.** `pytest tests/ -v` — 22 tests must pass.
9. **Spec before build.** Write spec in `specs/` before touching code.
10. **Verify with dry-run.** `python apply.py "URL" --dry-run` before marking done.

---

## Agent Modes

Pi reads mode files from `modes/`. To use:

- **Discover jobs:** "Read `modes/discover.md` and find jobs"
- **Prep interview:** "Read `modes/prep_interview.md` for Company X"
- **Batch run:** "Read `modes/batch.md` and process my queue"

## Running Tests

```bash
pytest tests/ -v        # 22 tests in ~0.2s
pytest tests/ -v -k scoring  # Filter by name
```

## Environment

Copy `.env.example` to `.env` and fill API keys. Required: `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `NOTION_TOKEN`, `NOTION_MASTER_RESUME_ID`.
