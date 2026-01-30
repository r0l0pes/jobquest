# JobQuest

Automated job application pipeline for Product Manager roles in the European startup ecosystem. Paste a URL, get a tailored PDF resume + ATS report + application answers + Notion tracking — one command.

## How It Works

```
python apply.py [url]
```

That single command runs a 10-step pipeline:

```
Job URL
  │
  ├─ 1. Scrape job posting (Greenhouse/Lever/Ashby/Workable API or HTML)
  ├─ 2. Read master resume from Notion
  ├─ 3. Tailor resume via Gemini (keyword extraction + natural insertion)
  ├─ 4. Write .tex file
  ├─ 5. Run ATS keyword coverage check (60-80% target)
  ├─ 6. Review & apply ATS edits (auto if ≥80%, asks you if <80%)
  ├─ 7. Compile PDF via pdflatex
  ├─ 8. Generate Q&A answers (company research + Applicant's voice)
  ├─ 9. Create Notion tracker entry
  └─ 10. Open form filler (browser opens, you review and submit)
          │ 
          ▼
     YOU click Submit
```

Everything is automated except the final submission — the system never applies on your behalf.

## Two Operating Modes

| Mode | When | What |
|------|------|------|
| **Pipeline** (`apply.py`) | Daily use — processing job applications | Gemini (free) handles LLM tasks, Python scripts handle automation |
| **Claude Code** | System development — adding features, fixing bugs | Use Claude Code when you need to modify the codebase itself |

The pipeline replaces Claude Code for the repetitive work (resume tailoring, ATS checks, Q&A writing) while keeping the full automation chain (PDF compilation, Notion sync, form filling).

## Quick Start

### 1. Setup

```bash
# Clone and enter project
cd JobSearch

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure `.env`

```bash
# Notion
NOTION_TOKEN=your_notion_integration_token
NOTION_MASTER_RESUME_ID=your_master_resume_page_id
NOTION_APPLICATIONS_DB_ID=your_applications_database_id
NOTION_QA_TEMPLATES_DB_ID=your_qa_templates_database_id
NOTION_SKILLS_KEYWORDS_DB_ID=your_skills_keywords_database_id

# LLM
GEMINI_API_KEY=your_gemini_api_key  # Free at https://aistudio.google.com/apikey

# Applicant
APPLICANT_NAME=Your Name
APPLICANT_EMAIL=your@email.com
APPLICANT_PHONE=+49 123 456789
APPLICANT_LINKEDIN=https://www.linkedin.com/in/yourprofile
APPLICANT_LOCATION=Berlin, Germany
```

### 3. Ensure pdflatex is installed

```bash
# macOS
brew install --cask mactex

# Linux
sudo apt-get install texlive-latex-base texlive-fonts-recommended
```

### 4. Run

```bash
# Full pipeline
python apply.py https://boards.greenhouse.io/company/jobs/12345

# With application questions
python apply.py https://jobs.lever.co/company/abc-123 \
  --questions "Why do you want to work here?;Describe your PM process"

# Skip form filler and Notion (just generate materials)
python apply.py https://example.com/jobs/pm --skip-form --skip-notion

# Preview what would happen
python apply.py https://example.com/jobs/pm --dry-run
```

## CLI Reference

```
python apply.py <job_url> [options]

Arguments:
  job_url                 URL of the job posting

Options:
  --questions TEXT         Application questions separated by semicolons
  --skip-form             Skip the browser form filler
  --skip-notion           Skip Notion database entry
  --model {gemini}        LLM provider (default: gemini)
  --dry-run               Show planned steps without executing
  -h, --help              Show help
```

## Output

Each run creates a directory under `output/`:

```
output/CompanyName_2026-01-30/
  ├── resume_tailored_CompanyName.tex     # Tailored LaTeX
  ├── resume_tailored_CompanyName.pdf     # Compiled PDF
  ├── ats_report_CompanyName.json         # Keyword coverage data
  ├── ats_report_CompanyName.md           # Human-readable ATS report
  ├── qa_CompanyName.md                   # Generated answers
  ├── form_data_CompanyName.json          # Form filler data
  └── pipeline_context.json               # Debug context (on error)
```

## Project Structure

```
JobSearch/
├── apply.py                    # Pipeline orchestrator (main entry point)
├── config.py                   # Environment config loader
├── batch_job_search.py         # Bulk job discovery via DuckDuckGo
├── requirements.txt            # Python dependencies
├── .env                        # Secrets (not in git)
│
├── modules/
│   ├── llm_client.py           # LLM abstraction (Gemini, pluggable)
│   ├── job_scraper.py          # ATS APIs + HTML scraping + company research
│   ├── pipeline.py             # 10 pipeline step functions
│   └── parsers.py              # LLM output parsing (LaTeX, JSON, Q&A)
│
├── scripts/
│   ├── notion_reader.py        # Read Notion pages/databases
│   ├── notion_tracker.py       # Create/update Notion entries
│   ├── notion_db_setup.py      # Initialize Notion DB schema
│   ├── render_pdf.py           # LaTeX → PDF via pdflatex
│   └── form_filler.py          # Playwright ATS form automation
│
├── prompts/
│   ├── resume_tailor.md        # LLM prompt: keyword extraction + LaTeX generation
│   ├── ats_check.md            # LLM prompt: coverage analysis + edit proposals
│   ├── qa_generator.md         # LLM prompt: application answers in Rodrigo's voice
│   └── jobquest_system_prompt.md  # Full system prompt for chat-based LLMs
│
├── templates/
│   └── resume.tex              # LaTeX resume template (structural reference)
│
├── .agent/skills/              # Claude Code agentic skills (for development mode)
│   ├── resume-tailor/SKILL.md
│   ├── ats-fixer/SKILL.md
│   └── qa-generator/SKILL.md
│
└── output/                     # Generated files (per-run directories)
```

## Supported ATS Platforms

The scraper detects and uses structured APIs when available:

| Platform | Detection | Method |
|----------|-----------|--------|
| Greenhouse | `boards.greenhouse.io` URLs | Public JSON API (includes application questions) |
| Lever | `jobs.lever.co` URLs | Public Postings API v0 |
| Ashby | `jobs.ashbyhq.com` URLs | Public GraphQL API |
| Workable | `apply.workable.com` URLs | Public Widget API |
| Everything else | Any URL | HTML scraping with Playwright fallback |

## Key Principles

**Human-in-the-loop.** The system never auto-submits. Form filler opens a browser and waits for you to review and click Submit.

**Honest materials.** All resume content comes from a pre-validated master resume in Notion. The system only repositions and emphasizes existing skills — it never fabricates experience or metrics.

**ATS-aware, not ATS-obsessed.** Targets 60-80% keyword coverage using semantic matching. Above 80% risks over-optimization. Modern ATS flags keyword stuffing.

**Rodrigo's voice.** Q&A answers are direct, builder-focused, metric-backed, and free of corporate buzzwords. No "passionate," no "synergy," no "I believe my experience aligns."

## Scripts Reference

Each script works standalone:

```bash
# Read master resume from Notion
venv/bin/python scripts/notion_reader.py page <page_id> --text

# Read a Notion database
venv/bin/python scripts/notion_reader.py database <db_id>

# Create application entry in Notion
venv/bin/python scripts/notion_tracker.py create \
  --title "Senior PM" --company "StartupX" --url "https://..."

# Update application status
venv/bin/python scripts/notion_tracker.py update \
  --page-id <page_id> --status "Interview"

# Compile LaTeX to PDF
venv/bin/python scripts/render_pdf.py output/resume.tex

# Fill application form (opens browser)
venv/bin/python scripts/form_filler.py \
  --url https://boards.greenhouse.io/company/jobs/123 \
  --resume-pdf output/resume.pdf \
  --data-file output/form_data.json

# Bulk job discovery
python batch_job_search.py

# Inspect Notion database schema
venv/bin/python scripts/notion_db_setup.py inspect

# Repair missing Notion properties
venv/bin/python scripts/notion_db_setup.py repair
```

## Safety

- The system **never** auto-submits applications
- The form filler opens a visible browser and pauses for manual review
- All metrics and experience come from pre-validated master documents
- Resume tailoring only adds keywords for skills the candidate actually has
- No scope inflation: "coordinated" stays "coordinated," never becomes "led"
