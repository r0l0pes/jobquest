# Spec 006: Job Market Optimization — Q1 2026 Trends

**Priority:** P1–P5
**Status:** Partially Implemented
**Date:** 2026-05-27
**Last Updated:** 2026-05-27

## Implementation Status

| Priority | Item | Status | Commit / Notes |
|----------|------|--------|----------------|
| P1 | Tighten same-company dedup (`>= 1`) | ❌ Not In Code | Handoff claimed done but `scripts/discover_jobs.py` still shows `>= 2`. Needs fix. |
| P2 | Add Google Jobs to discover queries | ❌ Not In Code | Handoff claimed done but `QUERY_CATALOG` has zero Google queries. Needs fix. |
| P3 | Rebalance remote vs onsite query ratio | ❌ Not Started | Shift ~5 remote queries to city-specific (Berlin, Munich, Barcelona, Madrid) |
| P4 | Source conversion tracking script | ❌ Not Started | New script: read `data/applications.json`, compute per-source interview rate |
| P5 | Ghost job heuristics | ❌ Not Started | Needs tracker data accumulation first |

**Note:** P1 and P2 were marked done in `SESSION_HANDOFF.md` but the changes were never committed to `scripts/discover_jobs.py`. They need to be re-applied.

---

**Original spec below:**

## Summary

The Q1 2026 job market is the slowest on record (108 days median to first offer). The report validates the pipeline's core strategy (tailored resumes = 2x interview rate) but reveals concrete opportunities to improve conversion at the sourcing and volume-control stages.

---

## Priority 1 (P1) — Tighten Same-Company Dedup ✅ DONE (2026-05-27)

**Problem:** `scripts/discover_jobs.py` capped at 2 jobs per company. The report shows 2-3 apps to the same company drops interview rate 24% (6.07% → 4.64%).

**Done:** `company_counts.get(company, 0) >= 2` changed to `>= 1` in `deduplicate_jobs()`. At most 1 job per company in the queue. Manual additions are unaffected.

---

## Priority 2 (P2) — Add Google Jobs to Discover Queries ✅ DONE (2026-05-27)

**Problem:** Google Jobs converts at 7.12% per application — 2.4x LinkedIn (2.94%). The discovery catalog had zero Google queries.

**Done:**
- 4 Google Jobs queries added to `QUERY_CATALOG` (DE + ES, generalist/growth/AI)
- `infer_source()` now recognizes `google.com/search` URLs and returns `"google"`

---

## Priority 3 (P3) — Rebalance Remote vs Onsite Query Ratio

**Problem:** ~15 of 38 queries target remote-only roles. The report shows remote converts at 3.63% vs onsite 5.76% — 37% worse due to competition. Over-indexing on remote wastes discovery capacity.

**Change:**
- Shift ~5 remote queries to city-specific ones (Berlin, Munich, Barcelona, Madrid)
- Keep remote queries for the best-remote-first boards (We Work Remotely, Remote OK, Himalayas)
- Target: 70% Germany/Spain city-specific, 30% remote

**Effort:** Query replacement in catalog, ~5 min

---

## Priority 4 (P4) — Source Conversion Tracking

**Problem:** Job source is captured (`source` field in queue + tracker entries) but never analyzed. You don't know which sources actually produce interviews.

**Spec:**
- Add a small aggregation script (`scripts/source_analytics.py` or similar) that:
  1. Reads `data/applications.json` for tracker entries with `source` + `status` fields
  2. Computes per-source: apps sent, interviews received, interview rate
  3. Outputs a table to stdout
- No UI needed — CLI output is fine. Data for decision-making.
- Run manually after 20-30 applications to kill low-converting sources

**Effort:** ~50 lines Python, 15 min

---

## Priority 5 (P5) — Ghost Job Heuristics

**Problem:** 93% of job seekers hit ghost postings. The pipeline's URL verification only catches 404s — not listings that look real but never respond.

**Spec:**
- Track stale URLs in the tracker: URL with no status change after 30 days → flag as suspected ghost
- Build a `blocked_domains` list (like the Franz Heinfling skiplist) from domains that produce multiple ghost URLs
- Emit a warning when >50% of applications from one source go silent after 30 days
- This is quality-of-life, not blocking — P5 because it requires tracker data accumulation first

**Effort:** ~80 lines, 30 min (but needs tracker data first)

---

## Priority Rankings

| # | Item | Why This Priority |
|---|------|-------------------|
| 1 | Same-company dedup | Near-zero effort, measurable downside avoided |
| 2 | Google Jobs queries | 2.4x better per-app conversion than LinkedIn, trivially cheap |
| 3 | Remote/onsite rebalance | Frees discovery capacity for higher-converting onsite roles |
| 4 | Source analytics | Unlocks data-driven sourcing decisions after ~20 apps |
| 5 | Ghost job heuristics | Needs tracker data to accumulate first |

---

## Implementation Notes

- Items P1-P3 are changes to existing files (`scripts/discover_jobs.py`)
- P4 needs a new script
- P5 can piggyback on P4's tracker data reader
- All changes are independent — no ordering dependency
