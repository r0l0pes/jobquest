# JobQuest — Claude Code Guide

JobQuest is an automated job application pipeline. Given a job posting URL, it produces a tailored PDF resume, ATS keyword report, Q&A answers, and a Notion tracker entry. It is a personal tool for Rodrigo Lopes, a Senior PM based in Berlin.

---

## Architecture Overview

```
apply.py / web_ui.py           ← Entry points (CLI and Gradio browser UI)
    ├── config.py                   ← Centralised env/config loader
    └── modules/pipeline.py         ← 9-step pipeline orchestrator
            ├── modules/llm_client.py    ← Multi-provider LLM (two-tier: writing + ATS)
            ├── modules/job_scraper.py   ← ATS APIs + HTML + Firecrawl + Playwright
            ├── modules/parsers.py       ← Output parsing utilities
            ├── scripts/notion_reader.py ← Read master resume from Notion
            ├── scripts/notion_tracker.py← Create Notion application entry
            ├── scripts/render_pdf.py    ← LaTeX → PDF via pdflatex
            ├── scripts/form_filler.py   ← Automated form filling
            └── scripts/notion_db_setup.py ← Notion database initialisation
```

**Key directories:**
- `modules/` — Core logic imported by entry points
- `scripts/` — Subprocess utilities called via `subprocess.run()`, output JSON
- `prompts/` — LLM prompt templates as `.md` files, loaded at runtime
- `templates/` — `resume.tex` master LaTeX template
- `output/` — Generated artefacts per run (`CompanyName_YYYY-MM-DD/`)
- `.agent/skills/` — Claude Code agent skill definitions

---

## Running the Project

**Python version:** 3.14 (via Homebrew: `/opt/homebrew/opt/python@3.14/bin/python3.14`)

```bash
# Activate virtual environment
source venv/bin/activate

# Browser UI (recommended)
python web_ui.py          # → http://127.0.0.1:7860

# CLI
python apply.py "JOB_URL"
python apply.py "JOB_URL" --company-url "https://company.com"
python apply.py "JOB_URL" --questions "Why this role?" --provider groq
python apply.py "JOB_URL" --dry-run   # preview only, no execution

# Batch job search from a markdown company list
python batch_job_search.py companies.md
```

**System dependency:** `pdflatex` must be installed (`brew install --cask mactex` on macOS).

---

## Environment Setup

Copy `.env.example` to `.env` and fill in values. Required fields:

```env
LLM_PROVIDER=gemini                    # gemini | groq | sambanova (ATS check step 5 only)
WRITING_PROVIDER=deepseek              # deepseek | openrouter | anthropic | gemini | groq | sambanova
GEMINI_API_KEY=...
DEEPSEEK_API_KEY=...                   # primary writing provider (~$0.008/app with caching)
NOTION_TOKEN=...
NOTION_APPLICATIONS_DB_ID=...
NOTION_MASTER_RESUME_ID=...
NOTION_QA_TEMPLATES_DB_ID=...
NOTION_SKILLS_KEYWORDS_DB_ID=...
APPLICANT_NAME=...
APPLICANT_EMAIL=...
APPLICANT_PHONE=...
APPLICANT_LINKEDIN=...
APPLICANT_LOCATION=...
```

Optional (enable fallback/enhanced scraping):
```env
GROQ_API_KEY=...
SAMBANOVA_API_KEY=...
OPENROUTER_API_KEY=...                 # writing fallback (Qwen3.5-397B, ~$0.014/app)
ANTHROPIC_API_KEY=...                  # writing last resort (Haiku 4.5, ~$0.06/app)
FIRECRAWL_API_KEY=...
RESUME_VARIANT=Tech-First              # Tech-First | Exp-First
```

---

## The 9-Step Pipeline

Each step receives and returns an enriched `ctx` dict:

1. Scrape job posting (structured API or HTML fallback)
2. Read master resume from Notion
3. Tailor resume via LLM (keyword extraction + natural insertion)
4. Write `.tex` file
5. Run ATS keyword coverage check (target: 60–80%)
6. Review & apply ATS edits (interactive in CLI, auto-apply in UI mode)
7. Compile PDF via `pdflatex`
8. Generate Q&A answers
9. Create Notion tracker entry

---

## Key Architectural Patterns

### LLM Provider Abstraction (`modules/llm_client.py`)

Two separate client tiers — never mix them:

**ATS check (step 5):** `LLM_PROVIDER` env var selects the provider. `FallbackClient` wraps `GeminiClient`, `GroqClient`, `SambaNovaClient`. On rate-limit, tries next model within provider, then next provider (Gemini 3.1 Pro → Groq → SambaNova).

**Writing steps (3, 6, 8):** `create_writing_client()` reads `WRITING_PROVIDER` env var (default: `deepseek`). Returns a `_WritingFallbackClient` that tries providers in order: DeepSeek V3.2 → OpenRouter/Qwen3.5-397B → Anthropic/Haiku 4.5 → Gemini → Groq → SambaNova. The fallback triggers on ANY error from the current provider (not just rate limits), so a bad API key or 400 error will still fall through gracefully.

Concrete clients: `GeminiClient`, `GroqClient`, `SambaNovaClient`, `DeepSeekClient`, `OpenRouterClient`, `AnthropicClient`. Never bypass this abstraction when adding LLM calls.

### Prompts as Files (`prompts/`)
All LLM prompts live in `prompts/*.md` and are loaded at runtime with `_load_prompt()`. Do not inline prompt text in Python files. This keeps prompts easy to iterate on and reduces Claude Code token usage when sharing code context.

Prompt files:
- `jobquest_system_prompt.md` — Master system prompt used across the pipeline
- `rodrigo-voice.md` — Voice, tone, banned phrases, and writing quality rules. Injected as system prompt prefix for steps 3 and 8. Single source of truth for all writing style rules.
- `resume_tailor.md` — Resume tailoring instructions (task-specific only; voice rules are in rodrigo-voice.md)
- `ats_check.md` — ATS keyword analysis instructions
- `qa_generator.md` — Q&A and cover letter generation instructions (task-specific only; voice rules are in rodrigo-voice.md)

### Subprocess Isolation (`scripts/`)
Scripts called via `subprocess.run()` return JSON on stdout. This isolates Notion calls and PDF rendering from the main pipeline. Follow this pattern for new external integrations.

### Web Scraping Hierarchy (`modules/job_scraper.py`)

**Job posting scraping:**
```
Known ATS platform? → Structured API (Greenhouse / Lever / Ashby / Workable / Personio / Screenloop)
Unknown platform?   → HTML scraping
                       → Playwright headless browser (if HTML is thin/JS-heavy)
                         → crawl4ai (if Playwright thin/SPA)
                           → Firecrawl (if FIRECRAWL_API_KEY set and still thin)
```

**Company research scraping** (step 8, Q&A generation):
```
Company URL provided? → Playwright (free, JS-rendering, one browser instance for up to 5 pages)
                          → crawl4ai (free, if Playwright returns all "Homepage" — SPA trap)
                            → Firecrawl (paid, if both above fail, requires API key)
                              → Plain HTML fetch (last resort)
No URL provided?      → Web search (Google → DuckDuckGo fallback)
```

The `_discover_important_pages()` function finds relevant pages (about, solutions, customers, blog, etc.) by crawling nav links before fetching. Playwright is always tried first; crawl4ai catches JS-heavy SPAs (React/Next.js) where Playwright returns the same homepage shell for every route. Firecrawl is last to avoid spending paid credits.

Add new ATS platforms to the structured API layer first; only fall through to HTML when necessary.

### Non-Interactive Mode
`pipeline.py` accepts an `interactive=False` flag used by `web_ui.py` to skip ATS review prompts and auto-apply edits. Any new interactive steps must respect this flag.

### Parser Resilience (`modules/parsers.py`)
Parsers strip `<think>...</think>` blocks (from DeepSeek-style reasoning models) before extracting LaTeX, JSON, or markdown from LLM responses. Any new parser functions must also handle these tokens.

`fix_markdown_lists()` is applied after every LLM LaTeX response (steps 3 and 6). It converts bare `- item` lines under `\section*{}` headings into proper `\begin{itemize}...\end{itemize}` blocks. This corrects a common LLM formatting failure in Certifications, Languages, and Education sections.

---

## Key Dependencies

Managed via `requirements.txt`:
- `google-generativeai` — Gemini LLM API
- `notion-client` — Notion API integration
- `playwright` — Headless browser for scraping
- `beautifulsoup4` — HTML parsing
- `rich` — Terminal formatting
- `python-dotenv` — Environment variable management
- `gradio` — Web UI framework (installed separately)
- `crawl4ai` — SPA-aware scraping fallback (free, no API key)
- `firecrawl-py` — Enhanced web scraping (optional, paid)

---

## Tests and Linting

There are currently no automated tests or linters configured. Manual validation uses `--dry-run`.

If adding tests, use **pytest**. If adding a linter, use **ruff**.

---

## Output Artefacts

Each run writes to `output/CompanyName_YYYY-MM-DD/`:

```
resume_tailored_*.tex       ← LaTeX source
resume_tailored_*.pdf       ← Ready to upload
ats_report_*.json           ← Structured keyword analysis
ats_report_*.md             ← Human-readable ATS report
qa_*.md                     ← Application answers
pipeline_context.json       ← Full ctx dict for debugging
```

---

## Agent Skills (`.agent/skills/`)

Three skills are defined for use within Claude Code sessions:
- `resume-tailor/` — Tailor a resume for a specific job posting
- `ats-fixer/` — Fix ATS keyword coverage gaps
- `qa-generator/` — Generate application answers

Refer to the `SKILL.md` in each directory before invoking or modifying a skill.

---

## MCP Integration

`.mcp.json` configures the **Context7** MCP server, which provides real-time SDK documentation during development. Use `mcp__context7__resolve-library-id` + `mcp__context7__query-docs` when working with Notion, Gemini, or Gradio APIs to avoid outdated patterns.

---

## Core Rules for This Codebase

- **Never fabricate resume content.** The resume tailoring pipeline only adds keywords for skills Rodrigo actually has. Do not modify this constraint.
- **Never auto-submit applications.** JobQuest generates materials; Rodrigo submits manually.
- **Keep prompts honest.** ATS keyword insertion must be natural — never stuff.
- **Preserve verified metrics.** Numbers and scope in the master resume must not be altered.
- **Minimal changes.** This is a personal productivity tool. Avoid over-engineering.
- **No em dashes anywhere** in generated output (resumes, cover letters, Q&A answers). Use commas, colons, or sentence breaks instead. This applies to prompts and any text written by Claude Code as well.
- **Writing quality rules live in `prompts/rodrigo-voice.md`.** This is the single source of truth for banned phrases, LLM tells, voice tone, and writing quality tests. `resume_tailor.md` and `qa_generator.md` contain only task-specific instructions. Do not add writing style rules to the task prompts — put them in rodrigo-voice.md.

---

## Supported Job Platforms

| Platform | URL Pattern | Scraper Type |
|----------|-------------|--------------|
| Greenhouse | `boards.greenhouse.io`, `job-boards.eu.greenhouse.io` | JSON API |
| Lever | `jobs.lever.co` | Postings API v0 |
| Ashby | `jobs.ashbyhq.com` | GraphQL API |
| Workable | `apply.workable.com` | Widget API |
| Personio | `*.jobs.personio.de/com` | HTML + JSON |
| Screenloop | `app.screenloop.com` | HTML scraping |
| Others | Any URL | HTML → Firecrawl → Playwright |
