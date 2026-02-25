---
name: qa-generator
description: Generate Q&A answers and cover letter for a job application. Use when the pipeline has already run but application questions need answers, or when answers need to be regenerated. Reads from the existing run context.
---

If the pipeline has already run, the Q&A is at `output/<Company>_<date>/qa_<Company>.md`. Read it first.

To regenerate (if the pipeline run already has a `pipeline_context.json`):

```bash
source venv/bin/activate && python apply.py "$JOB_URL" --questions "Question 1 | Question 2"
```

If reviewing existing answers, check for:
- Any banned phrases from `prompts/rodrigo-voice.md` (em dashes, LLM tells, "passionate", "excited", etc.)
- Any claim without a number behind it — either add the metric or cut the claim
- Any sentence starting with "I" in the cover letter opening
- Any restating of the company's own description back at them
- Closing that thanks rather than names their specific challenge

Apply the So What, Prove It, and Earn Your Place tests to every sentence.
