---
name: ats-fixer
description: Review ATS keyword coverage for the latest tailored resume and apply fixes. Use when the pipeline ATS score is below 60% or when step 5 flags missing keywords. Reads the ATS report from the run directory.
---

Find the most recent run directory:

```bash
ls -t output/ | head -1
```

Read `ats_report_<Company>.md` from that directory. Then read `resume_tailored_<Company>.tex`.

For each keyword in the report marked MISSING (not N/A):
1. Check if Rodrigo actually has evidence for this skill in `pipeline_context.json` or the tailoring brief
2. If yes: find the most natural insertion point in the LaTeX and propose a minimal edit
3. If no: mark as N/A — do not add fabricated skills

Present proposed edits one at a time. For each:
```
KEYWORD: [term]
LOCATION: [section / company / bullet context]
BEFORE: [current text]
AFTER: [proposed text]
```

Never add skills Rodrigo does not have. Never stuff keywords unnaturally. If there is no clean insertion point, skip the keyword.

After user confirms, apply edits to the `.tex` file and recompile:
```bash
source venv/bin/activate && python scripts/render_pdf.py output/<dir>/resume_tailored_<Company>.tex
```
