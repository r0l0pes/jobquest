# JobQuest

Automated job application pipeline. Discovery, tailoring, scoring, tracking, and editing — all from a single URL or one-click launcher.

## What It Does

1. **Discover** — Exa API searches for PM jobs across the web. Pop-up modal on the Discovery tab asks time range (7d/24h) and whether to keep or clear existing positions.
2. **Evaluate Fit** — Pre-pipeline gate scores job fit (0-100) across Skills, Experience, Behavioral/Culture, Location, Career Alignment. Blocks bad-fit jobs before LLM costs.
3. **Tailor** — 3-stage LLM resume tailoring with adversarial review (separate Gemini 3 Flash call critiques for fabrications, missed keywords, tone). ATS keyword coverage check. Q&A generation with behavioral tone + salary context. Interview prep. Cover letter compilation.
4. **Score & Track** — 0-100 pipeline score from ATS match, compliance, company research, AI signals, behavioral fit. Sortable HTML tracker with editable modals. Skill gap analysis via `--upskill`.

Manual apply only. No auto-submission.

## One-Click Launch

Double-click **`JobQuest.command`** — it starts both servers and opens 3 browser tabs:

| Tab | URL | What it shows |
|-----|-----|---------------|
| **Pipeline** | `http://127.0.0.1:7860` | 3 parallel application slots with Gradio UI |
| **Tracker** | `http://127.0.0.1:7880` | Application list with editable Q&A, Cover Letter, Resume |
| **Discovery** | `http://127.0.0.1:7880/queue` | Job queue with automatic pop-up to run discovery |

## Quick Launch (Manual)

```bash
source venv/bin/activate
python serve_tracker.py --port 7880   # Tracker + Discovery + API
python web_ui.py                       # Pipeline UI
```

## Pipeline

```
Job URL
  │
  ├─  1. Scrape job posting (6 ATS platforms + HTML fallback)
  ├─  2. Read master resume from Notion (cached per 3 variants)
  ├─  3. Fit Evaluation Gate — score fit (0-100), block poor fits
  ├─  4. Tailor resume via LLM (analysis → LaTeX → compliance)
  ├─  5. Write .tex file
  ├─  6. Review drafts (adversarial) — Gemini 3 Flash critiques
  ├─  7. Apply reviewer feedback — JSON edits + narrative fixes
  ├─  8. Run ATS keyword coverage check
  ├─  9. Review & apply ATS edits
  ├─ 10. Compile PDF via pdflatex (+ compile-and-inspect loop)
  ├─ 11. Generate Q&A answers (+ behavioral tone + salary context)
  ├─ 12. Generate interview prep (STAR examples, likely questions)
  ├─ 13. Compute pipeline score (0-100)
  ├─ 14. (Optional) Compile cover letter PDF
  └─ 15. Save to tracker (data/applications.json, dedup by URL)
          │
          ▼
     Output/Company_YYYY-MM-DD/
       ├── Resume_Rodrigo-Lopes.tex + .pdf
       ├── Cover-Letter_RodrigoLopes.tex + .pdf (optional)
       ├── qa_Company.md
       ├── interview_prep_Company.md
       ├── ats_report_Company.md
       ├── tailoring_brief_Company.md
       ├── review_feedback_Company.md
       └── pipeline_context.json
```

## Agent Modes

Pi reads mode files from `modes/`:

| Mode           | File                      | What it does                                                                   |
| -------------- | ------------------------- | ------------------------------------------------------------------------------ |
| Discover       | `modes/discover.md`       | Search 20+ platforms (12 remote-only + local), output to `data/job_queue.html` |
| Interview Prep | `modes/prep_interview.md` | Company-specific research + STAR story bank                                    |
| Batch          | `modes/batch.md`          | Process job queue sequentially or via web UI                                   |
| Upskill        | `modes/upskill.md`        | Skill gap analysis (hard skill diff + LLM synthesis → heatmap → learning plan) |

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

# CLI usage
python apply.py "JOB_URL"
python apply.py "JOB_URL" --skip-reviewer    # Skip adversarial review
python apply.py --upskill                     # Skill gap analysis
python apply.py --dry-run "JOB_URL"           # Dry-run without LLM calls
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

**Reviewer (step 6):** Separate Gemini 3 Flash client with Flash-Lite fallback — different model from the writing chain for true adversarial perspective.

**Fit evaluation (step 3):** Gemini 3.1 Flash-Lite — short classification task doesn't need the full writing chain.

**Upskill (CLI):** Gemini 3.1 Flash-Lite for gap synthesis.

**ATS check (step 5):** User-selectable provider with cross-provider fallback.
Primary (Gemini / Groq / SambaNova / OpenRouter) → rate-limit → next in chain.

## Tracker Editing

The tracker supports in-place editing of all application artifacts:

| Column | Click | Modal offers |
|--------|-------|--------------|
| **Q&A** | Q&A button | Editable textarea + Save |
| **Cover** | Cover button | Editable .tex content + Save + Recompile PDF + Remove |
| **Resume** | Resume button | Editable .tex content + Save + Recompile PDF + Remove |

Clicking **Recompile PDF** sends the edited content to the server, which writes the updated `.tex` to disk and runs `render_pdf.py` to regenerate the PDF. Changes persist when you click "Save Changes" in the toolbar.

## Project Structure

```
JobQuest/
├── AGENTS.md                  ← Pi reads this first
├── JobQuest.command           ← One-click launcher (3 browser tabs)
├── apply.py                   ← CLI pipeline orchestrator (+ --skip-reviewer, --upskill)
├── web_ui.py                  ← Gradio UI (3 parallel slots)
├── serve_tracker.py           ← Tracker + Discovery + API server
├── config.py
├── modules/                   ← Core pipeline logic
│   ├── pipeline.py            ← 15 steps + fit scoring + behavioral profile
│   ├── llm_client.py          ← Multi-provider LLM (Gemini, Groq, SambaNova, OpenAI, Anthropic)
│   ├── upskill.py             ← Skill gap analysis (5-pass pipeline)
│   └── parsers.py
├── scripts/                   ← Subprocess utilities
│   ├── render_pdf.py          ← pdflatex + compile-and-inspect loop
│   ├── salary_lookup.py       ← Salary benchmarking (fuzzy company matching)
│   └── form_filler.py
├── prompts/                   ← LLM prompt templates (10 prompts)
│   ├── reviewer.md            ← Adversarial review (Part A JSON + Part B narrative)
│   ├── behavioral_profile.md  ← Behavioral profile template
│   └── fit_evaluation.md      ← Fit scoring with behavioral/Culture dimension
├── modes/                     ← Pi agent instructions (4 modes)
├── data/
│   ├── applications.json      ← 21+ entries, auto-saved by pipeline
│   ├── tracker.html           ← Editable tracker UI
│   └── job_queue.html         ← Discovery queue with pop-up modal
├── output/                    ← Per-application output dirs
├── upskill/                   ← Skill gap analysis report output
├── specs/                     ← 11 feature specifications
├── tests/                     ← pytest (186 tests)
└── templates/                 ← LaTeX resume + cover letter templates
```

## Testing

```bash
pytest tests/ -v               # 186 tests in ~1.4s
pytest tests/ -v -k reviewer   # Filter reviewer tests
pytest tests/ -v -k salary     # Filter salary benchmarking tests
pytest tests/ -v -k upskill    # Filter upskill gap analysis tests
pytest tests/ -v -k behavior   # Filter behavioral profile tests
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
