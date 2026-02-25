---
name: resume-tailor
description: Tailor Rodrigo's resume for a specific job posting. Use when given a job URL and asked to generate a customised resume. Runs the full 9-step JobQuest pipeline.
---

# Resume Tailor Skill

## When to Use

- User provides a job URL and asks to tailor the resume
- User says "run the pipeline for [URL]"
- User says "apply to [company]"

## How to Run

The pipeline handles everything. Do not try to do the tailoring manually.

```bash
source venv/bin/activate
python apply.py "JOB_URL"

# With optional args:
python apply.py "JOB_URL" --company-url "https://company.com"
python apply.py "JOB_URL" --questions "Why this role?"
python apply.py "JOB_URL" --dry-run   # preview, no execution
```

## What the Pipeline Does

**Step 3 uses a two-stage approach:**

- **3a (analysis):** Free-tier LLM reads the JD + master resume, produces a structured tailoring brief. This identifies role priorities, which bullets to touch, what the summary strategy is, and what to leave alone.
- **3b (writing):** Writing LLM generates LaTeX using the brief as explicit context — it executes a plan rather than figuring one out mid-generation.

The brief is saved to `output/<Company>_<date>/tailoring_brief_<Company>.md` for inspection.

## Output

Each run writes to `output/<Company>_YYYY-MM-DD/`:
- `resume_tailored_<Company>.tex` — LaTeX source
- `resume_tailored_<Company>.pdf` — Ready to upload
- `tailoring_brief_<Company>.md` — JD analysis used for tailoring
- `ats_report_<Company>.json` / `.md` — ATS keyword coverage
- `qa_<Company>.md` — Application answers

## When Pipeline Output Looks Wrong

If the tailored resume has quality issues, check the tailoring brief first:
```bash
cat output/<Company>_<date>/tailoring_brief_<Company>.md
```

If the brief is wrong (misidentified priorities, wrong bullet targets), the problem is in `prompts/jd_analysis.md`. Fix the prompt and re-run.

If the brief is correct but the LaTeX is wrong, the problem is in `prompts/resume_tailor.md` or the specific model output. Check `tailor_raw` in `pipeline_context.json`.

## LaTeX Format Reference

Experience entry format (what the pipeline actually outputs):
```latex
\vspace{8pt}
\noindent\textbf{Company}, Role Title \hfill Dates, Location
\begin{itemize}[leftmargin=*, label=$\bullet$, itemsep=4pt, parsep=0pt]
\item Achievement with metric...
\end{itemize}
```

Skills section (must be itemize, never paragraph):
```latex
\section*{Skills \& Tools}
\begin{itemize}[leftmargin=*, label=$\bullet$, itemsep=3pt, parsep=0pt]
\item \textbf{Category Name:} Skill 1, Skill 2, Skill 3
\end{itemize}
```

## Critical Rules

- Never fabricate experience, metrics, or skills
- Never change job titles ("Senior Product Manager" stays as-is)
- Never swap tool names (Amplitude stays Amplitude)
- Never use em dashes anywhere in output
- Verified metrics are sacred — never alter them
