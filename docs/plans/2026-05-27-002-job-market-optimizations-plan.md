---
title: Job Market Optimizations — Q1 2026 Trends
type: feat
status: active
date: 2026-05-27
origin: specs/006-job-market-optimizations.md
---

# Job Market Optimizations — Q1 2026 Trends

## Summary

Apply five data-backed optimizations from the Huntr Q1 2026 report to the job discovery pipeline: tighten same-company deduplication to 1 job max, add Google Jobs search queries, shift ~5 remote queries to city-specific (Berlin/Munich/Barcelona/Madrid), build a source conversion tracking script, and lay groundwork for ghost job heuristics. All changes are isolated to `scripts/discover_jobs.py` and one new analytics script.

---

## Problem Frame

The Q1 2026 job market is the slowest on record (108 days median to first offer). The Huntr report validates tailored resumes improve interview rates but reveals concrete inefficiencies in the current discovery pipeline:

1. **Same-company over-application**: 2-3 apps to the same company drops interview rate 24% (6.07% → 4.64%). Current dedup allows 2 jobs per company.
2. **Missing high-conversion source**: Google Jobs converts at 7.12% — 2.4x LinkedIn (2.94%). Current query catalog has zero Google Jobs queries.
3. **Remote over-indexing**: ~15 of 38 queries target remote-only. Remote converts at 3.63% vs onsite 5.76% — 37% worse.
4. **No source analytics**: Job source is captured but never analyzed. Cannot data-drive sourcing decisions.
5. **Ghost job vulnerability**: 93% of job seekers hit ghost postings. No heuristic detection.

---

## Requirements

- R1. Same-company deduplication must cap at 1 job per company in discovery output.
- R2. Query catalog must include Google Jobs search queries for DE and ES, all three role types.
- R3. ~5 remote queries must shift to city-specific (Berlin, Munich, Barcelona, Madrid).
- R4. Source conversion tracking script must read `data/applications.json`, compute per-source metrics (apps sent, interviews, rate), output table to stdout.
- R5. Ghost job groundwork: script must flag applications with no status change after 30 days.
- R6. All changes must not break existing `scripts/discover_jobs.py` functionality.
- R7. All 22+ existing tests must pass.

---

## Scope Boundaries

- In scope: Query catalog edits, dedup logic change, new analytics script, tracker data reader.
- Out of scope: Web UI changes, Notion integration changes, LLM-based query generation.
- Deferred to Follow-Up Work: Building a `blocked_domains` list from accumulated ghost data; automatic query rebalancing based on live conversion rates.

---

## Context & Research

### Relevant Code and Patterns

- `scripts/discover_jobs.py` — job discovery script with `QUERY_CATALOG`, `deduplicate_jobs()`, `infer_source()`
- `data/applications.json` — tracker data with `source`, `status`, `date` fields
- `data/job_queue.html` / `data/job_queue.md` — discovery output formats
- Existing dedup: `company_counts.get(company, 0) >= 2` (line ~504)

### Institutional Learnings

- Query catalog uses a 4-tuple: `(query_string, role_type, location, board)`
- `infer_source()` maps URLs to source names for tracker entries
- Discovery output is consumed by `data/job_queue.html` — no server needed
- Manual additions to the queue bypass dedup (intentional)

---

## Key Technical Decisions

- **Google Jobs queries**: Use `google.com/search` URLs with `ibp=htl;jobs` parameters. `infer_source()` already has a pattern for URL-based source detection — extend it.
- **City-specific queries**: Replace the lowest-ROI remote queries (4dayweek, jobspresso, flexjobs, nodesk duplicates) with Berlin/Munich/Barcelona/Madrid city-specific queries.
- **Source analytics**: Standalone script, not integrated into pipeline. Run manually after ~20 applications. Keeps the pipeline lean.
- **Ghost job flagging**: Part of the analytics script, not a separate module. Reads tracker data, flags stale entries.

---

## Open Questions

### Resolved During Planning

- **Q: Which remote queries to replace?** → Replace the niche-board remote queries (4dayweek, jobspresso, flexjobs, nodesk) rather than the top-tier ones (We Work Remotely, Remote OK, Himalayas, Wellfound).
- **Q: Google Jobs query format?** → `site:google.com/search?q=...&ibp=htl;jobs` or direct search with Jobs filter. Use standard Google search queries with role + location.

### Deferred to Implementation

- **Q: Exact city query wording** — tuned during implementation for natural language match.

---

## Implementation Units

### U1. Tighten same-company dedup to 1 job max

**Goal:** Reduce same-company over-application per Huntr report findings.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Modify: `scripts/discover_jobs.py`
- Test: `tests/test_discover_jobs.py` (new)

**Approach:**
- Change `deduplicate_jobs()`: `company_counts.get(company, 0) >= 2` → `>= 1`
- Update docstring to reflect the new limit.

**Execution note:** TDD — write test first asserting max 1 job per company, then make the change.

**Test scenarios:**
- **Happy path:** Two jobs from same company → second one dropped
- **Edge case:** Exactly 1 job per company → kept
- **Edge case:** Manual additions bypass dedup (verify they still do)
- **Edge case:** Different titles from same company → still deduped to 1

**Verification:**
- `pytest tests/test_discover_jobs.py -v` passes
- `python scripts/discover_jobs.py` produces output with no duplicate companies

---

### U2. Add Google Jobs queries to catalog

**Goal:** Capture the highest-conversion job source (7.12% vs LinkedIn 2.94%).

**Requirements:** R2

**Dependencies:** None (can parallelize with U1)

**Files:**
- Modify: `scripts/discover_jobs.py`
- Test: `tests/test_discover_jobs.py`

**Approach:**
- Add 4 Google Jobs queries to `QUERY_CATALOG`:
  - Growth PM — Germany (Google)
  - AI PM — Germany (Google)
  - Generalist PM — Spain (Google)
  - Growth PM — Spain (Google)
- Set `board="google"` for these queries.
- Update `infer_source()` to recognize `google.com/search` URLs and return `"google"`.

**Test scenarios:**
- **Happy path:** Google queries present in catalog
- **Happy path:** `infer_source("https://www.google.com/search?q=...")` returns `"google"`
- **Edge case:** Non-Google URL still returns correct source

**Verification:**
- `pytest tests/test_discover_jobs.py -v` passes
- `python scripts/discover_jobs.py` includes Google queries in output

---

### U3. Rebalance remote vs city-specific queries

**Goal:** Shift discovery capacity from lower-converting remote roles to higher-converting onsite roles.

**Requirements:** R3

**Dependencies:** None (can parallelize with U1, U2)

**Files:**
- Modify: `scripts/discover_jobs.py`
- Test: `tests/test_discover_jobs.py`

**Approach:**
- Remove 4-5 lowest-ROI remote queries (4dayweek duplicates, jobspresso, flexjobs, nodesk duplicates).
- Add 4-5 city-specific queries:
  - Berlin: 2 queries (growth + generalist)
  - Munich: 1 query (generalist)
  - Barcelona: 1 query (growth)
  - Madrid: 1 query (generalist)
- Keep top remote boards: We Work Remotely, Remote OK, Himalayas, Wellfound.

**Test scenarios:**
- **Happy path:** Remote query count reduced by ~5
- **Happy path:** City-specific queries present for Berlin, Munich, Barcelona, Madrid
- **Edge case:** Total query count remains ~38 (balanced swap)

**Verification:**
- `pytest tests/test_discover_jobs.py -v` passes
- `python scripts/discover_jobs.py` outputs expected query distribution

---

### U4. Build source conversion tracking script

**Goal:** Enable data-driven sourcing decisions after ~20 applications.

**Requirements:** R4, R5

**Dependencies:** None (can parallelize with U1-U3)

**Files:**
- Create: `scripts/source_analytics.py`
- Test: `tests/test_source_analytics.py` (new)

**Approach:**
- Read `data/applications.json`.
- Aggregate by `source` field:
  - `apps_sent`: count of entries per source
  - `interviews`: count where `status` contains "interview" (case-insensitive)
  - `interview_rate`: `interviews / apps_sent` as percentage
- Sort by `interview_rate` descending.
- Print formatted table to stdout.
- Ghost job flagging: For each application, if `status` is still "applied" and `date` is >30 days old, increment `suspected_ghosts` per source.
- Emit warning if any source has >50% suspected ghosts.

**Test scenarios:**
- **Happy path:** Script reads applications.json and outputs table with correct rates
- **Happy path:** Multiple sources aggregated correctly
- **Edge case:** Empty applications.json → graceful message, no crash
- **Edge case:** Missing `source` or `status` fields → handled gracefully
- **Edge case:** Division by zero (0 apps) → handled gracefully
- **Integration:** Ghost flagging correctly identifies 30+ day "applied" entries

**Verification:**
- `pytest tests/test_source_analytics.py -v` passes
- `python scripts/source_analytics.py` produces readable table with real data

---

### U5. Update smoke tests and verify all tests pass

**Goal:** Ensure no regressions in the discovery pipeline.

**Requirements:** R6, R7

**Dependencies:** U1, U2, U3, U4

**Files:**
- Modify: `tests/test_smoke.py` (if discover_jobs step count or behavior changes)
- Test: `tests/test_discover_jobs.py`, `tests/test_source_analytics.py`

**Approach:**
- Run `pytest tests/ -v` — all 22+ tests pass.
- Run `python scripts/discover_jobs.py` — verify output format unchanged, query count ~38, no duplicate companies.
- Run `python scripts/source_analytics.py` — verify output with real or mock data.

**Test scenarios:**
- **Integration:** Full test suite passes
- **Integration:** Discovery script runs without errors
- **Integration:** Analytics script runs without errors

**Verification:**
- `pytest tests/ -v` — all tests pass

---

## System-Wide Impact

- **Interaction graph:** `scripts/discover_jobs.py` output consumed by `data/job_queue.html`. No downstream changes needed.
- **Error propagation:** Analytics script is standalone — failures do not affect pipeline.
- **State lifecycle risks:** `data/applications.json` is append-only; analytics script is read-only.
- **API surface parity:** No CLI or UI changes for the pipeline itself.
- **Unchanged invariants:** Pipeline steps, LLM calls, form filler, tracker HTML rendering.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Google Jobs queries may return non-job results | Use specific role + location + "jobs" keywords. Monitor first run. |
| City-specific queries may overlap with existing Germany/Spain queries | Use city name explicitly ("Berlin", "Munich") to narrow results. |
| Analytics script breaks if `applications.json` schema changes | Handle missing fields gracefully with `.get()` defaults. |

---

## Documentation / Operational Notes

- Document `scripts/source_analytics.py` usage in README or AGENTS.md.
- Note the dedup change for manual queue additions (still bypass dedup).

---

## Sources & References

- **Origin document:** `specs/006-job-market-optimizations.md`
- Related code: `scripts/discover_jobs.py`, `data/applications.json`
- External: [Huntr Q1 2026 Job Search Trends Report](https://huntr.co/research/job-search-trends-q1-2026)
