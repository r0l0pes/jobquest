# JobQuest

Automated job application pipeline. Paste a URL, get a tailored PDF resume + ATS report + application answers + Notion tracking.

<img width="1566" height="1035" alt="Screenshot 2026-02-04 at 19 19 39" src="https://github.com/user-attachments/assets/43b96708-5ea7-4425-9de0-62ea30fb4894" />

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
FIRECRAWL_API_KEY=...   # optional, better JS page scraping
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
- **ATS-aware**: Targets 60-80% keyword coverage, avoids stuffing

---

## Technical Architecture

### API Integrations

| Service | Purpose | API Type |
|---------|---------|----------|
| **Notion** | Master resume storage, application tracking | REST API |
| **Greenhouse** | Job scraping | Public JSON API |
| **Lever** | Job scraping | Postings API v0 |
| **Ashby** | Job scraping | GraphQL API |
| **Workable** | Job scraping | Widget API |
| **Personio** | Job scraping | HTML + JSON extraction |
| **Screenloop** | Job scraping | HTML scraping |
| **DuckDuckGo** | Company research fallback | HTML scraping |
| **Firecrawl** | Enhanced web scraping (JS, anti-bot) | REST API |

### LLM Fallback Strategy

```
Primary Provider (user-selected)
    │
    ├─ Rate limit? → Try next model within provider
    │                  (Gemini: 3-flash → 2.5-flash → 2.5-flash-lite → 3-pro → 2.5-pro)
    │
    └─ All models exhausted? → Try next provider
                                  (Gemini → Groq → SambaNova)
```

**Why this design:**
- Free tiers have per-model limits (Gemini: 20 req/day per model, 5 models = 100 total)
- Different providers have different rate limit windows
- Automatic fallback means no manual intervention during batch runs

### Web Scraping Strategy

**Job posting scraping:**
```
Job URL
    │
    ├─ Known ATS? → Structured API (Greenhouse, Lever, Ashby, Workable, Personio, Screenloop)
    │
    └─ Unknown?  → HTML scraping
                     │
                     └─ JS-heavy? → Playwright (free, headless Chromium)
                                       │
                                       └─ Still thin? → Firecrawl (if configured)
```

**Company research scraping** (used in step 8 for Q&A context):
```
Company URL provided?
    │
    ├─ Playwright first (free) — discovers up to 5 pages via nav links, renders JS
    │
    └─ Thin result? → Firecrawl (paid, only as fallback)
                         │
                         └─ Failed? → Plain HTML → Web search
```

Playwright is always tried first to avoid spending Firecrawl credits unnecessarily.

### Token Optimization

We considered several approaches to reduce Claude Code token usage:

1. **Prompts in files** (implemented): All LLM prompts stored in `prompts/*.md`, loaded at runtime
2. **Templates over generation**: LaTeX structure comes from master template, LLM only modifies content
3. **Structured extraction**: Job scraping uses APIs when available (cheaper than LLM parsing HTML)
4. **Context7 MCP** (configured): Provides up-to-date documentation to avoid outdated API calls

**Pipeline vs Claude Code split:**
- Repetitive tasks (resume tailoring, ATS checks) → Gemini/Groq (free)
- System development → Claude Code (when modifying the codebase)

### MCP Integration

`.mcp.json` configures Model Context Protocol servers:

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    }
  }
}
```

**Context7** provides real-time documentation for APIs (Google Gemini, Notion, etc.) to avoid errors from outdated SDK usage.

---

## Changelog

### Feb 2026
- Playwright-first company research (free, JS-rendering); Firecrawl now fallback only
- Hardcoded resume taglines per variant (Growth PM / Generalist) — LLM can no longer change them
- Notion API pinned to stable version (2022-06-28) to fix step 2 timeouts after notion-client v2.7.0
- 24h local cache for master resume (avoids Notion on repeat runs; validates content length)
- Generalist tagline updated to "End-to-end ownership. Outcomes delivered." (from real Berlin/Barcelona JD research)
- Resume tailor prompt: explicit rules against shortening bullets and changing job titles
- Browser UI with 3 parallel forms
- Multi-provider LLM support (Gemini, Groq, SambaNova)
- Cross-provider fallback on rate limits
- Per-provider usage tracking
- Added Personio, Screenloop, Greenhouse EU scrapers
- `--company-url` flag for direct company research
- Firecrawl integration for enhanced JS page scraping
- Non-interactive mode for ATS review (auto-apply edits when running from UI)

### Jan 2026
- Initial pipeline implementation
- Greenhouse, Lever, Ashby, Workable scrapers
- Notion integration for resume + tracking
- ATS keyword optimization
