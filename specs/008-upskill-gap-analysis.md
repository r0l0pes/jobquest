# P8: /upskill — Skill Gap Analysis & Learning Plan

**Status:** Spec
**Date:** 2026-06-04
**Source:** ai-job-search `/upskill` skill — Skill gap heatmap + learning resources

---

## What

A new CLI command and pipeline mode that analyzes tracked job applications
against the candidate profile to identify skill gaps, build a priority-graded
heatmap, and generate a learning plan with web-searched study resources,
estimated study hours, and a dependency-ordered study sequence.

## Why

JobQuest tracks applications in `data/applications.json` — 21 entries and
growing. This data is a goldmine for career planning:

- Which skills keep appearing in job descriptions that Rodrigo doesn't have?
- What would make him a stronger candidate for the roles he's targeting?
- What should he learn next, and in what order?

ai-job-search's `/upskill` command answers these questions. It turns the
application tracker from a passive log into an active career development tool.

## How

### Modes

**Aggregate mode:** `python apply.py --upskill`
- Analyzes all tracked applications
- Builds skill frequency map weighted by fit score
- Lower fit = higher gap weight (that role exposed more gaps)

**Targeted mode:** `python apply.py --upskill "JOB_URL"`
- Analyzes a single job posting
- No fit weighting needed

### Workflow

**Pass 1: Hard Skill Diff**
1. For each tracked application: extract required/preferred skills from
   `notes`, `role`, `sector` fields
2. Build skill frequency map: count how many jobs mention each skill
3. Apply fit weight: `(100 - fit_score) / 100` × occurrence
4. Diff against candidate profile (`01-candidate-profile.md` or master resume)
5. Be generous — "Python" covers "Python scripting"
6. Remaining = hard skill gap list, ranked by score descending

**Pass 2: LLM Synthesis**
Reason about gaps not caught by hard skill diff:
- Domain knowledge (industry familiarity)
- Soft skills (communication, leadership patterns in JDs)
- Tooling and process (CI/CD, MLOps, cloud services)
- Certifications

**Pass 3: Gap Heatmap**

| Priority | Skill/Area | Type | Gap Source |
|---|---|---|---|
| Critical | Kubernetes | Hard | 5/21 jobs, score 4.2 |
| High | CI/CD pipelines | Tooling | LLM synthesis |
| Medium | AWS (advanced) | Hard | 3/21 jobs, score 2.1 |

**Pass 4: Learning Plan**
For Critical + High gaps (Medium if <5 total gaps):
1. WebSearch for current study resources
2. Pick 2-3 resources per gap
3. Write study direction (what to skip, where to start)
4. Estimate time to working proficiency

**Pass 5: Study Order**
Dependency-ordered sequence with time estimates.

### Output

Saved to `upskill/report-YYYY-MM-DD.md`:

```markdown
# Upskill Report — 2026-06-04
**Mode:** Aggregate (21 jobs analyzed)

## Since Last Report
**Gaps closed:** (none — first run)
**New gaps:** Kubernetes, CI/CD pipelines, AWS advanced

## Gap Heatmap
| Priority | Skill / Area | Type | Gap Source |
...

## Learning Plan
### Cloud & Infrastructure
**Kubernetes** `[Hard]` — ~20h
- [Resource with URL] — hands-on labs
- [Resource with URL] — reference docs

Study direction: You already know Docker — skip containers basics.
Start at Pod scheduling, work through Services and Deployments.

## Suggested Study Order
| # | Topic | Type | Est. Time | Note |
...

**Total estimated time: ~70h**
```

### Diff Against Previous Reports

If a previous report exists:
- **Gaps closed:** skills now in profile that were in previous heatmap
- **New gaps:** skills in current heatmap not in previous

### Integration

- New CLI flag: `--upskill` (aggregate) or `--upskill "URL"` (targeted)
- Also accessible via Pi agent mode: `modes/upskill.md`
- Writes reports to `upskill/` directory

This is a Won't-tier feature per ICE prioritization — lowest priority,
highest effort. Only build after the active job search period.

## Changes

| File | Change |
|---|---|
| `modules/pipeline.py` | Add `run_upskill()` function |
| `apply.py` | Add `--upskill` CLI flag |
| `modes/upskill.md` | **Create** — Pi agent mode for upskill |
| `upskill/` | **Create** directory for report output |

## Implementation Plan

1. Write `run_upskill()` — pass 1 hard skill diff against `applications.json`
2. Add LLM synthesis pass — domain/soft/tooling gap reasoning
3. Build heatmap table
4. Add WebSearch for study resources
5. Build learning plan with study order
6. Save report with diff logic
7. Add `--upskill` flag to `apply.py`
8. Create `modes/upskill.md` for Pi agent mode

## Test Scenarios

| Category | Scenario |
|---|---|
| Happy path | Aggregate mode analyzes 21 jobs, produces heatmap + learning plan |
| Happy path | Targeted mode analyzes single URL, produces focused report |
| Edge case | No previous report → no diff section |
| Edge case | Previous report exists → shows gaps closed + new gaps |
| Edge case | No applications tracked → "No data" message |
| Edge case | All skills already in profile → empty heatmap |
| Integration | Report saved to `upskill/report-YYYY-MM-DD.md` |
| Integration | Pi mode `modes/upskill.md` invokes the command |
