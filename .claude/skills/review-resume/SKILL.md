---
name: review-resume
description: Review the latest tailored resume against the tailoring brief. Use after running /resume-tailor when the output quality looks off. Reads the brief and LaTeX from the most recent run directory and flags where the resume didn't follow the plan.
---

Find the most recent run directory:

```bash
ls -t output/ | head -1
```

Then read both files from that directory:
1. `tailoring_brief_<Company>.md` — the plan the writing model was given
2. `resume_tailored_<Company>.tex` — what it actually produced

Compare them and flag:
- **Brief says "do not change" but LaTeX changed it** — regression
- **Brief identifies a bullet insertion target but the keyword is missing from the LaTeX** — missed insertion
- **Summary strategy in brief vs summary in LaTeX** — did it follow the theme order and use the specified JD language?
- **"De-emphasize" sections that are actually foregrounded in the LaTeX** — wrong emphasis

For each issue found, output:
```
ISSUE: [brief instruction] vs [what the LaTeX actually does]
SEVERITY: HIGH / MEDIUM / LOW
FIX: [minimal edit to the .tex file]
```

Only flag real discrepancies. If the output matches the brief, say so in one line and stop.
