# P2: Fit Scoring

**Status:** Implemented
**Date:** 2026-05-08

## What

A 0-100 pipeline score computed automatically after the pipeline runs, using
data the pipeline already generates. No new LLM calls.

## Why

With 100-160 applications in 4 weeks, you need to know which ones are worth
following up on — without manually reviewing every output.

## How

### Two-tier filtering

**Tier 1 — Quick Pass (before pipeline):**

- Role title matches one of the 40+ target titles in the 30-day roadmap
- Location: Germany / Spain / Remote EU
- Not a VP / Head / Director role (unless IC-heavy JD)

**Tier 2 — Pipeline Score (after pipeline, automatic):**

| Dimension              | Source                        | Weight |
| ---------------------- | ----------------------------- | ------ |
| ATS keyword coverage   | Step 5 `coverage_pct`         | 40%    |
| Brief compliance       | Step 3c `tailor_review.md`    | 20%    |
| Company research depth | Step 8 research quality       | 20%    |
| JD AI signals          | `_is_ai_heavy_jd()`           | 10%    |
| Resume variant quality | User-selected variant fits JD | 10%    |

### Score interpretation

| Score  | Label  | What to do               |
| ------ | ------ | ------------------------ |
| 80-100 | STRONG | Apply immediately        |
| 60-79  | GOOD   | Apply, check Q&A quality |
| 40-59  | WEAK   | Skip unless scarce       |
| 0-39   | SKIP   | Don't apply              |

### Output

Score is displayed in the CLI summary, saved to `pipeline_context.json`,
and written to `data/applications.json` for the tracker.
