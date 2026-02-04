# JobQuest Command Reference

## Quick Launch (Easiest)

**Double-click:** `JobQuest.command` in Finder → Opens browser UI at http://127.0.0.1:7860

Or drag it to your Dock for one-click access.

---

## Browser UI

```bash
cd /Users/carvalho/Documents/VibeCoding/JobSearch && source venv/bin/activate && python web_ui.py
```

The browser UI provides:
- Form fields for Job URL, Company URL, Questions
- Provider selection (Gemini, Groq, SambaNova)
- Per-provider usage tracking
- Real-time pipeline output
- Recent applications list

---

## Direct Command

### Basic
```bash
cd /Users/carvalho/Documents/VibeCoding/JobSearch && source venv/bin/activate && python apply.py "JOB_URL"
```

### With Company URL (for better research)
```bash
python apply.py "JOB_URL" --company-url "https://company.com"
```

### With Questions
```bash
python apply.py "JOB_URL" --questions "Question 1" --questions "Question 2"
```

### Full Example
```bash
cd /Users/carvalho/Documents/VibeCoding/JobSearch && source venv/bin/activate && python apply.py "https://jobs.lever.co/company/abc" --company-url "https://company.com" --questions "Why this role?" --questions "Cover letter" --questions "Describe your experience"
```

---

## Flags

| Flag | Description |
|------|-------------|
| `--company-url "URL"` | Company website for research (recommended) |
| `--questions "Q"` | Application question (repeat for multiple) |
| `--skip-notion` | Skip Notion entry |
| `--dry-run` | Preview without running |

---

## Rate Limits & Fallback

**Automatic fallback**: When one provider hits rate limits, the system automatically tries the next available provider.

| Provider | Daily Limit | Get API Key |
|----------|-------------|-------------|
| Gemini | ~100 requests | [aistudio.google.com](https://aistudio.google.com/apikey) |
| Groq | 1,000 requests | [console.groq.com](https://console.groq.com) |
| SambaNova | ~500 requests | [cloud.sambanova.ai](https://cloud.sambanova.ai) |

**Combined capacity**: ~1,600 requests/day (~400 applications)

Set primary provider in `.env`: `LLM_PROVIDER=gemini` (default)

Add backup providers by adding their API keys to `.env`:
```
GEMINI_API_KEY=...
GROQ_API_KEY=...
SAMBANOVA_API_KEY=...
```

### Recommended Approach
- Each application: ~4 API calls
- Browser UI shows per-provider usage
- Fallback is automatic when limits are reached

---

## Questions Guidelines

### Yes/No Questions
Always answer **"Yes"** then provide evidence.

### Cover Letters
250-350 words. Structure:
1. Hook about company (specific, not generic)
2. Relevant experience with metrics
3. What you'll bring

### Common Questions to Add
```
--questions "Cover letter"
--questions "Why do you want this role?"
--questions "Describe your PM experience"
--questions "Have you worked with [X]?"
```

---

## Output Locations

```
output/
└── CompanyName_YYYY-MM-DD/
    ├── resume_tailored_*.tex
    ├── resume_tailored_*.pdf
    ├── ats_report_*.json
    ├── ats_report_*.md
    ├── qa_*.md          ← Answers here
    └── form_data_*.json
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Rate limited | Automatic fallback to next provider (if API keys configured) |
| All providers exhausted | Add more API keys to `.env`, or wait until quotas reset |
| Notion error | Usually Resume Variant property - retries automatically |
| Company "unknown" | Add company URL in the form |
| No Q&A generated | Add questions in the form (one per line) |
