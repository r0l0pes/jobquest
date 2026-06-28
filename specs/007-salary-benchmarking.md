# P7: Salary Benchmarking Hook — Optional Compensation Context

**Status:** Spec
**Date:** 2026-06-04
**Source:** ai-job-search `salary_lookup.py` — Salary benchmarking tool

---

## What

Add an optional salary benchmarking capability to the pipeline. When salary
data is available, look up the target company during fit evaluation and
include compensation context in Q&A answers. When no data exists, skip silently.

## Why

Salary expectations questions appear in Q&A forms ("What are your salary
expectations?"). Currently JobQuest has no compensation context — the LLM
either skips the question or guesses.

ai-job-search includes `salary_lookup.py` with:
- Fuzzy company name matching (handles spelling variants, legal suffixes)
- City filtering
- Structured JSON output with category indices
- BYO-data design (works with any salary source)

This gives the LLM concrete data to answer salary questions intelligently.

## How

### Port `salary_lookup.py`

The tool is already Python — minimal porting needed:

```bash
cp salary_lookup.py scripts/
```

Requires `salary_data.json` in the project root. If the file doesn't exist,
all salary steps are silently skipped.

### Data Format (`salary_data.json`)

```json
{
  "metadata": {
    "source": "Glassdoor / Levels.fyi / Union statistics",
    "currency": "EUR",
    "index_label": "Comp Index",
    "index_baseline": 100,
    "baseline_description": "Index 100 = market median for PM roles in Berlin"
  },
  "companies": [
    {
      "company": "Zalando SE",
      "city": "Berlin",
      "categories": {
        "base_salary": { "count": 45, "index": 115.3 },
        "total_comp": { "count": 32, "index": 122.1 }
      }
    }
  ]
}
```

### Integration Points

**Fit evaluation (spec 001):** After scoring, if salary data exists:

```
### Salary Benchmark
| Metric | Value |
|---|---|
| Base salary index | 115.3 (+15.3% vs market) |
| Total comp index | 122.1 (+22.1% vs market) |
```

**Q&A generation (step 8):** When Q&A includes salary expectations question,
inject benchmark data so the LLM can produce an informed answer:

```
## Salary Context
[Company] compensation: Base salary ~15% above Berlin PM market median.
Total compensation ~22% above. N=45 salary data points.
Use this to answer salary expectation questions if asked.
```

### Skipping When No Data

The tool checks for `salary_data.json` at startup. If absent:
- Fit evaluation omits salary section
- Q&A generation omits salary context injection
- No errors, no warnings, no user-facing changes

## Changes

| File | Change |
|---|---|
| `scripts/salary_lookup.py` | **Create** — port from ai-job-search |
| `salary_data.json` | **Create** if user populates it (gitignored — private data) |
| `modules/pipeline.py` | Add salary lookup in fit eval and Q&A steps |
| `.gitignore` | Add `salary_data.json` |

## Implementation Plan

1. Port `salary_lookup.py` from ai-job-search to `scripts/`
2. Add salary lookup to `step_evaluate_fit()` — conditional on file existence
3. Add salary injection to `step_generate_qa()` — only for salary-related Qs
4. Add `salary_data.json` to `.gitignore`
5. Document the data format in `tools/README_SALARY_TOOL.md`

## Test Scenarios

| Category | Scenario |
|---|---|
| Happy path | Company found in salary data → benchmark shown in fit eval |
| Happy path | Salary Q in application → informed answer using benchmark |
| Edge case | `salary_data.json` missing → salary steps skipped silently |
| Edge case | Company not found in data → "No data" note in fit eval |
| Edge case | City filter narrows results correctly |
