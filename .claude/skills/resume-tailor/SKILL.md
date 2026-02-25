---
name: resume-tailor
description: Run the JobQuest pipeline to tailor Rodrigo's resume for a job posting. Use when given a job URL. Runs apply.py which handles scraping, two-stage tailoring, ATS check, PDF compilation, and Notion tracking.
argument-hint: "[job URL] [--company-url URL] [--questions 'text'] [--dry-run]"
---

Run the JobQuest pipeline for the given job URL:

```bash
source venv/bin/activate && python apply.py $ARGUMENTS
```

After the run completes, check `output/` for the latest directory. It contains:
- `tailoring_brief_<Company>.md` — the JD analysis used to drive tailoring (inspect this if quality is off)
- `resume_tailored_<Company>.pdf` — ready to upload
- `ats_report_<Company>.md` — keyword coverage
- `qa_<Company>.md` — application answers

If output looks wrong, read the tailoring brief first. If the brief itself is wrong, the fix is in `prompts/jd_analysis.md`. If the brief is right but the LaTeX is wrong, run `/review-resume`.
