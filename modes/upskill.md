# Upskill Mode — Skill Gap Analysis & Learning Plan

Analyze tracked job applications against your candidate profile to identify
skill gaps, build a priority-graded heatmap, and generate a learning plan
with study directions and time estimates.

## Usage

### Aggregate mode (all tracked applications)

```bash
python apply.py --upskill
```

Analyzes all entries in `data/applications.json`. Builds a weighted frequency
map of skills mentioned across all roles, diffs against your master resume /
candidate profile, and ranks gaps by priority.

### Targeted mode (single job URL)

```bash
python apply.py --upskill "https://example.com/jobs/pm-123"
```

Analyzes only the specified job against your profile.

## Output

Reports are saved to `upskill/report-YYYY-MM-DD.md`:

- **Since Last Report:** Gaps closed and new gaps since previous report
- **Gap Heatmap:** Priority table (Critical / High / Medium) with skill, type, and source
- **Learning Plan:** Study directions, estimated time, and suggested order
- **Total estimated time:** Summary of hours needed

## How It Works

1. **Hard Skill Diff** — Extracts required/preferred skills from job notes,
   role titles, and sectors. Weighted by fit score (lower fit = higher gap
   weight). Diffs against master resume corpus.

2. **LLM Synthesis** — Uses Gemini Flash-Lite to identify domain knowledge,
   soft skills, and tooling/process gaps that keyword matching misses.

3. **Heatmap** — Priority tiers: Critical (5+ mentions), High (2+ mentions),
   Medium (rest). Sorted by descending priority and score.

4. **Learning Plan** — Study direction and estimated time for Critical+High
   gaps. Dependency-ordered sequence with total time estimate.

## Dependencies

- `data/applications.json` — populated by the pipeline
- `prompts/` or `.master_resume_cache_*.txt` — candidate profile for diffing
- Gemini API key for LLM synthesis pass (optional — falls back to rule-based)
