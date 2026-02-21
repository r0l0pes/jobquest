# JobQuest

Automated job application pipeline. Paste a URL, get a tailored PDF resume + ATS report + application answers + Notion tracking.

<img width="1566" height="1035" alt="Screenshot 2026-02-04 at 19 19 39" src="https://github.com/user-attachments/assets/43b96708-5ea7-4425-9de0-62ea30fb4894" />

## Quick Launch

**Double-click** `JobQuest.command` → Opens browser UI at http://127.0.0.1:7860

Or: `python web_ui.py`

The browser UI provides:
- 3 parallel application forms (run multiple jobs simultaneously)
- ATS provider selection for step 5 (Gemini, Groq, SambaNova — free tiers)
- Writing steps (3, 6, 8) always use the quality-first provider chain (DeepSeek → OpenRouter → Haiku)
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

## LLM Architecture

Two separate provider tiers — one for quality, one for speed.

**Writing steps (resume tailor, ATS edits, Q&A):** Paid quality-first chain with automatic fallback.

| Provider | Model | Cost/app | Get Key |
|----------|-------|----------|---------|
| DeepSeek V3.2 | deepseek-chat | ~$0.008 | [platform.deepseek.com](https://platform.deepseek.com) |
| OpenRouter | Qwen3.5-397B | ~$0.014 | [openrouter.ai](https://openrouter.ai) |
| Anthropic | Haiku 4.5 | ~$0.06 | [console.anthropic.com](https://console.anthropic.com) |

**ATS check step (step 5):** Free-tier providers with automatic fallback.

| Provider | Daily Limit | Get Key |
|----------|-------------|---------|
| Gemini 3.1 Pro | ~250 req | [aistudio.google.com](https://aistudio.google.com/apikey) |
| Groq | 1,000 req | [console.groq.com](https://console.groq.com) |
| SambaNova | ~500 req | [cloud.sambanova.ai](https://cloud.sambanova.ai) |

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
WRITING_PROVIDER=deepseek
DEEPSEEK_API_KEY=...    # primary writing provider
GEMINI_API_KEY=...      # ATS check step (free)
GROQ_API_KEY=...        # optional ATS fallback
SAMBANOVA_API_KEY=...   # optional ATS fallback
OPENROUTER_API_KEY=...  # optional writing fallback
ANTHROPIC_API_KEY=...   # optional writing last resort
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
│   ├── rodrigo-voice.md   # Shared voice/tone/banned phrases (injected into writing steps)
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

**Writing steps (3, 6, 8) — quality-first:**
```
DeepSeek V3.2 (primary, ~$0.008/app with prefix caching)
    │
    └─ Rate limit? → OpenRouter / Qwen3.5-397B (~$0.014/app)
                         │
                         └─ Rate limit? → Anthropic / Haiku 4.5 (~$0.06/app)
                                              │
                                              └─ Rate limit? → Gemini → Groq → SambaNova
```

**ATS check (step 5) — free-tier:**
```
User-selected provider (Gemini / Groq / SambaNova)
    │
    ├─ Rate limit? → Try next model within provider
    │                  (Gemini: 3.1-pro → 3-flash → 2.5-pro → 2.5-flash → 2.5-flash-lite)
    │
    └─ All models exhausted? → Try next provider (Gemini → Groq → SambaNova)
```

**Prompt caching:** DeepSeek V3.2 has automatic prefix caching. User prompt is ordered static-first (master resume, templates) then dynamic (job posting, questions), so the master resume is cached after the first application of the day.

### Web Scraping Strategy

**Job posting scraping:**
```
Job URL
    │
    ├─ Known ATS? → Structured API (Greenhouse, Lever, Ashby, Workable, Personio, Screenloop)
    │
    └─ Unknown?  → HTML scraping
                     │
                     ├─ JS-heavy? → Playwright (free, headless Chromium)
                     │
                     ├─ Still thin? → crawl4ai (free, better for SPAs)
                     │
                     └─ Still thin? → Firecrawl (if configured, best anti-bot)
```

**Company research scraping** (used in step 8 for Q&A context):
```
Company URL provided?
    │
    ├─ Playwright first (free) — discovers up to 5 pages via nav links
    │
    ├─ Thin result/SPA trap? → crawl4ai (free, handles JS routing)
    │
    └─ Still thin? → Firecrawl (paid, best markdown extraction)
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
- Writing steps (resume tailoring, ATS edits, Q&A) → DeepSeek V3.2 (~$0.008/app)
- ATS keyword check → Gemini/Groq/SambaNova (free)
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


