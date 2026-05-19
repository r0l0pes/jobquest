# JobQuest

Automated job application pipeline. Discovery, tailoring, scoring, and tracking — all from a single URL.

## What It Does

1. **Discover** — Agent finds jobs across LinkedIn, StepStone, Wellfound, We Work Remotely,
   Remote OK, Himalayas, Remotive, and more (via `modes/discover.md`)
2. **Tailor** — 3-stage LLM resume tailoring with ATS keyword coverage check
3. **Score** — 0-100 pipeline score from ATS match, compliance, company research, and AI signals
4. **Track** — Sortable HTML tracker with editable status, notes, and analytics

Manual apply only. No auto-submission.

## Quick Launch

```bash
# Web UI (3 parallel application slots)
python web_ui.py                    → http://127.0.0.1:7860

# CLI
python apply.py "JOB_URL"

# Tracker
python serve_tracker.py             → http://127.0.0.1:7878
```

## Pipeline

```
Job URL
  │
  ├─  1. Scrape job posting (6 ATS platforms + HTML fallback)
  ├─  2. Read master resume from Notion (cached per variant)
  ├─  3. Tailor resume via LLM (3-stage: analysis → LaTeX → compliance)
  ├─  4. Write .tex file
  ├─  5. Run ATS keyword coverage check
  ├─  6. Review & apply ATS edits
  ├─  7. Compile PDF via pdflatex
  ├─  8. Generate Q&A answers (with company research)
  ├─  9. Compute pipeline score (0-100)
  ├─ 10. Create Notion tracker entry
  └─ 11. (Optional) Open form filler
          │
          ▼
     Output: PDF + Q&A + score
```

## Agent Modes

Pi reads mode files from `modes/`:

| Mode           | File                      | What it does                                                                   |
| -------------- | ------------------------- | ------------------------------------------------------------------------------ |
| Discover       | `modes/discover.md`       | Search 20+ platforms (12 remote-only + local), output to `data/job_queue.html` |
| Interview Prep | `modes/prep_interview.md` | Company-specific research + STAR story bank                                    |
| Batch          | `modes/batch.md`          | Process job queue sequentially or via web UI                                   |

## Resume Variants

Three variants in Notion, toggled in the web UI:

| Variant    | Tagline                                                    |
| ---------- | ---------------------------------------------------------- |
| Growth PM  | "Experiments that accelerate revenue."                     |
| Generalist | "End-to-end ownership. Outcomes delivered."                |
| AI PM      | "GenAI product delivery. End-to-end, governance included." |

## Setup

```bash
# Install
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure .env (see .env.example)
GEMINI_API_KEY=...          # Required (free, aistudio.google.com)
GROQ_API_KEY=...            # Optional (free, console.groq.com)
SAMBANOVA_API_KEY=...       # Optional (free, cloud.sambanova.ai)
OPENCODE_API_KEY=...        # Optional (paid, opencode.go)
OPENROUTER_API_KEY=...      # Optional (paid, openrouter.ai)
NOTION_TOKEN=...
NOTION_MASTER_RESUME_ID=...

# Ensure pdflatex
brew install --cask mactex  # macOS
```

## LLM Providers

**Writing steps (3, 6, 8):** Free-first fallback chain — user selects primary model
via `--writing-model` CLI flag or web UI dropdown; falls back automatically on
rate-limit errors.

| Provider    | Model             | Tier | Rate Limit |
| ----------- | ----------------- | ---- | ---------- |
| Gemini      | 2.5 Pro           | Free | 25 RPD     |
| Gemini      | 3 Flash           | Free | 500 RPD    |
| Gemini      | 3.1 Flash-Lite    | Free | 1500 RPD   |
| OpenCode Go | Kimi K2.6         | Paid | —          |
| OpenRouter  | DeepSeek V4 Flash | Paid | —          |
| OpenRouter  | Qwen 3.5          | Paid | —          |
| Groq        | Llama 3.3 70B     | Free | 1000 RPD   |
| SambaNova   | Llama 3.1 405B    | Free | 30 RPM     |

**ATS check (step 5):** User-selectable provider with cross-provider fallback.
Primary (Gemini / Groq / SambaNova / OpenRouter) → rate-limit → next in chain.

## Output

```
output/CompanyName_YYYY-MM-DD/
  ├── tailoring_brief_*.md     # JD analysis
  ├── tailor_review_*.md       # Compliance check
  ├── resume_tailored_*.tex    # LaTeX source
  ├── resume_tailored_*.pdf    # Ready to upload
  ├── ats_report_*.md          # Keyword coverage
  ├── qa_*.md                  # Application answers
  └── pipeline_context.json    # Full context + score
```

## Project Structure

```
JobQuest/
├── AGENTS.md                  ← Pi reads this first
├── apply.py                   ← CLI pipeline
├── web_ui.py                  ← Gradio UI (3 slots)
├── serve_tracker.py           ← Tracker server
├── config.py
├── modules/                   ← Core logic
├── scripts/                   ← Subprocess utilities
├── prompts/                   ← LLM prompt templates
├── modes/                     ← Pi agent instructions
├── data/                      ← Tracker + job queue
├── specs/                     ← Feature specifications
├── tests/                     ← pytest (22 tests)
└── templates/                 ← LaTeX resume template
```

## Testing

```bash
pytest tests/ -v               # 22 tests in ~0.2s
```

## Supported Platforms

| Platform   | URL Pattern                                           |
| ---------- | ----------------------------------------------------- |
| Greenhouse | `boards.greenhouse.io`, `job-boards.eu.greenhouse.io` |
| Lever      | `jobs.lever.co`                                       |
| Ashby      | `jobs.ashbyhq.com`                                    |
| Workable   | `apply.workable.com`                                  |
| Personio   | `*.jobs.personio.de`, `*.jobs.personio.com`           |
| Screenloop | `app.screenloop.com`                                  |
| Others     | HTML scraping fallback                                |
