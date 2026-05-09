# JobQuest Command Reference

## Quick Launch

```bash
source venv/bin/activate

# Web UI (primary interface)
python web_ui.py                    → http://127.0.0.1:7860

# CLI
python apply.py "JOB_URL"
python apply.py "JOB_URL" --questions "Why this role?"
python apply.py "JOB_URL" --fill-form
python apply.py "JOB_URL" --dry-run

# Tracker
python serve_tracker.py             → http://127.0.0.1:7878

# Tests
pytest tests/ -v
```

## Web UI

3 parallel application slots. Each slot:

- Job URL + Company URL + Questions
- Resume variant: Growth PM / Generalist / AI-PM
- Writing model: DeepSeek V3 / Gemini 2.5 Flash / Gemini Flash / OpenRouter
- ATS provider: gemini / groq / sambanova

## Output

```
output/CompanyName_YYYY-MM-DD/
  ├── resume_tailored_*.pdf    ← Upload this
  ├── resume_tailored_*.tex
  ├── qa_*.md                  ← Copy-paste answers
  ├── ats_report_*.md
  └── pipeline_context.json    ← Score + full context
```

## Environment

Copy `.env.example` → `.env`. Required keys:

- `GEMINI_API_KEY` (free tier)
- `DEEPSEEK_API_KEY` (or another writing provider)
- `NOTION_TOKEN`, `NOTION_MASTER_RESUME_ID`
