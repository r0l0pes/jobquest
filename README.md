# JobQuest

Automated job application pipeline for Product Manager roles in the European startup ecosystem. Paste a URL, get a tailored PDF resume + ATS report + application answers + Notion tracking.

## Quick Launch

**Double-click** `JobQuest.command` → Opens browser UI at http://127.0.0.1:7860

Or: `python web_ui.py`

The browser UI provides:
- 3 parallel application forms (run multiple jobs simultaneously)
- Provider selection (Gemini, Groq, SambaNova)
- Per-provider usage tracking
- Real-time pipeline output

## How It Works

```
Job URL
  │
  ├─ 1. Scrape job posting (Greenhouse/Lever/Ashby/Workable/Personio/Screenloop)
  ├─ 2. Read master resume from Notion
  ├─ 3. Tailor resume via LLM (keyword extraction + natural insertion)
  ├─ 4. Write .tex file
  ├─ 5. Run ATS keyword coverage check (60-80% target)
  ├─ 6. Review & apply ATS edits
  ├─ 7. Compile PDF via pdflatex
  ├─ 8. Generate Q&A answers (company research + voice matching)
  └─ 9. Create Notion tracker entry
          │
          ▼
     Output: PDF + Q&A ready to copy/paste
```

## Multi-Provider LLM Support

Cross-provider fallback: if one provider hits rate limits, automatically tries the next.

| Provider | Daily Limit | Get Key |
|----------|-------------|---------|
| Gemini | ~100 req | [aistudio.google.com](https://aistudio.google.com/apikey) |
| Groq | 1,000 req | [console.groq.com](https://console.groq.com) |
| SambaNova | ~500 req | [cloud.sambanova.ai](https://cloud.sambanova.ai) |

**Combined capacity**: ~1,600 requests/day (~400 applications)

## CLI Usage

```bash
# Basic
python apply.py "https://jobs.lever.co/company/abc"

# With company URL (better research)
python apply.py "JOB_URL" --company-url "https://company.com"

# With application questions
python apply.py "JOB_URL" --questions "Why this role?" --questions "Cover letter"

# Select provider
python apply.py "JOB_URL" --provider groq

# Preview
python apply.py "JOB_URL" --dry-run
```

## Setup

```bash
# Install
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure .env (see .env.example)
GEMINI_API_KEY=...
GROQ_API_KEY=...        # optional, enables fallback
SAMBANOVA_API_KEY=...   # optional, enables fallback
NOTION_TOKEN=...
# ... (see .env.example for full list)

# Ensure pdflatex
brew install --cask mactex  # macOS
```

## Output

```
output/CompanyName_YYYY-MM-DD/
  ├── resume_tailored_*.pdf    # Ready to upload
  ├── qa_*.md                  # Answers to copy/paste
  ├── ats_report_*.md          # Keyword coverage
  └── pipeline_context.json    # Debug info
```

## Supported Platforms

| Platform | URL Pattern |
|----------|-------------|
| Greenhouse | `boards.greenhouse.io`, `job-boards.eu.greenhouse.io` |
| Lever | `jobs.lever.co` |
| Ashby | `jobs.ashbyhq.com` |
| Workable | `apply.workable.com` |
| Personio | `*.jobs.personio.de`, `*.jobs.personio.com` |
| Screenloop | `app.screenloop.com` |
| Others | HTML scraping fallback |

## Project Structure

```
JobQuest/
├── web_ui.py              # Browser UI (Gradio)
├── apply.py               # CLI pipeline orchestrator
├── JobQuest.command       # Double-click launcher
├── COMMANDS.md            # Full command reference
│
├── modules/
│   ├── llm_client.py      # Multi-provider LLM (Gemini/Groq/SambaNova + fallback)
│   ├── job_scraper.py     # ATS APIs + HTML scraping
│   └── pipeline.py        # 9 pipeline steps
│
├── prompts/
│   ├── resume_tailor.md   # Resume tailoring prompt
│   ├── ats_check.md       # ATS analysis prompt
│   └── qa_generator.md    # Q&A generation prompt
│
├── scripts/
│   ├── notion_tracker.py  # Notion integration
│   └── render_pdf.py      # LaTeX → PDF
│
└── templates/
    └── resume.tex         # Master LaTeX template
```

## Key Principles

- **Human-in-the-loop**: System generates materials, you submit
- **Honest materials**: Only uses skills from pre-validated master resume
- **Never say no**: Yes/No questions always answered "Yes" with evidence
- **ATS-aware**: Targets 60-80% keyword coverage, avoids stuffing

## Changelog

### Feb 2026
- Browser UI with 3 parallel forms
- Multi-provider LLM support (Gemini, Groq, SambaNova)
- Cross-provider fallback on rate limits
- Per-provider usage tracking
- Added Personio, Screenloop, Greenhouse EU scrapers
- `--company-url` flag for direct company research
- "Never say no" rule for Q&A
- Fixed LaTeX `\begin{document}` generation
- Removed form filler (manual submission preferred)

### Jan 2026
- Initial pipeline implementation
- Greenhouse, Lever, Ashby, Workable scrapers
- Notion integration for resume + tracking
- ATS keyword optimization
