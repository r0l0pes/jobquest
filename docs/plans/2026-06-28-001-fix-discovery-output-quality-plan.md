---
title: fix: Discovery output quality — location, remote, scraper, and company name filtering
type: fix
status: active
date: 2026-06-28
---

# fix: Discovery Output Quality — Location, Remote, Scraper, and Company Name Filtering

## Summary

Fix three post-retrieval filtering bugs and two quality gaps in the discovery pipeline: non-target jobs accepted as DE/ES, remote jobs silently rejected, scraper-farm domains leaking, company names extracted as numeric IDs, and Spain-targeted queries underrepresented. Add regression test coverage for the classification functions that currently have zero tests — six implementation units total.

---

## Problem Frame

The last discovery run (24h mode, June 28) found 30 jobs from 58 queries, but output quality was severely degraded:

- **0 remote jobs** despite 23 remote-targeted queries in the catalog
- **27/30 jobs** had generic "Germany"/"Spain" locations with no city
- **13/30 jobs** had garbage company names — numeric IDs ("2657353"), generic words ("Job", "Apply"), or domain fragments
- **4 jobs** were misclassified — US, UK, and Argentina postings tagged as Germany or Spain
- **9 jobs** came from known scraper-farm domains (liveblog365.com, likesyou.org)

The root causes are in `scripts/discover_jobs.py`'s `infer_location()` and `extract_company_from_url()` functions, plus an incomplete `skip_patterns` list. These are filtering bugs, not search query problems — the Exa API returns valid results, but the post-retrieval pipeline rejects good jobs and accepts bad ones.

---

## Requirements

- R1. Non-target locations (US, UK, Canada, India, Argentina, LATAM, APAC) must be rejected even when the query's `country_hint` is "de" or "es"
- R2. Remote-targeted queries (country_hint="remote") must produce accepted remote jobs when no non-EU signal is present
- R3. All `*.liveblog365.com` subdomains and `likesyou.org` must be blocked by the URL skip-pattern filter
- R4. Company names must not be extracted as numeric-only strings from URL slug segments
- R5. The query catalog must have roughly balanced DE and ES query counts
- R6. `infer_location()`, `extract_company_from_url()`, and `result_to_job()` must have unit test coverage for happy path, edge cases, and error paths
- R7. All 195 existing tests must continue to pass

---

## Scope Boundaries

- Fixes are confined to `scripts/discover_jobs.py` and a new `tests/test_discover_jobs.py`
- No changes to the tracker server (`serve_tracker.py`), the Exa API integration layer (`exa_search`), or the query deduplication logic
- No changes to `modes/discover.md` (the agent mode instructions)
- No changes to `data/job_queue.html` format or the JS-object persistence layer
- No architectural refactor of the `result_to_job()` pipeline — the 12-stage gate structure stays intact; only individual stages are tightened
- Existing query semantics are preserved — queries themselves are unchanged; only ES additions are appended

### Deferred to Follow-Up Work

- `startPublishedDate` datetime precision (date-only `isoformat()` creates a ~33-48h window for "24h" mode; switching to `datetime.utcnow()` would make it exact) — minor impact, deferred
- `clean_title()` aggressive suffix stripping (can truncate location signals before `infer_location` sees them) — deferred until a run shows this materially reducing yield
- Deduplication cap (hard max of 2 jobs per company) — separate improvement for when output volume justifies it
- Domain-trust-first location classification (using `stepstone.de` = DE, `himalayas.app` = remote as primary signals rather than text heuristics) — architectural refactor deferred to a future plan
- Extracting `skip_patterns` and `QUERY_CATALOG` to standalone config files — maintenance convenience, not quality-critical

---

## Context & Research

### Relevant Code and Patterns

- `scripts/discover_jobs.py:237-277` — `infer_location()`: three-tier whitelist (DE cities → ES cities → EU-remote signals), then country_hint fallback, then reject
- `scripts/discover_jobs.py:431-580` — `result_to_job()`: 12-stage pipeline (URL presence → title length → PM signal → exclusion signals → news indicators → clickbait → skip_patterns → company extraction → location inference → garbage check → source inference → return dict)
- `scripts/discover_jobs.py:311-377` — `extract_company_from_url()`: subdomain patterns → path patterns → `/job/` slug extraction with dash-split
- `scripts/discover_jobs.py:66-137` — `QUERY_CATALOG`: list of `(query, role_type, country_hint, expected_source)` tuples
- `scripts/discover_jobs.py:488-545` — `skip_patterns`: list of ~70 raw regex patterns applied via `re.search(pat, url_lower)`
- `tests/test_tracker.py:134-252` — `TestJobsHubDiscover`: 8 tests using `monkeypatch` with `tmp_path` for file isolation and mock `urllib.request.urlopen` for API call capture
- `tests/test_tracker.py:253-356` — `TestDiscoveryAsync`: 4 tests spinning up real `HTTPServer` on hardcoded ports, testing `/api/discover` and `/api/discover/status`

### Institutional Learnings

- Prior discovery fix plan `docs/plans/2026-06-07-001-fix-discovery-returns-nothing-plan.md` documented the architecture shift to direct Exa API calls (bypassing pi's broken `web_search` tool), removal of URL verification (HEAD requests killed 86% of valid URLs), and the whitelist-only location strategy. This plan explicitly kept `country_hint` fallback unchanged and excluded query catalog changes — the quality fixes here are the logical next phase.
- No `docs/solutions/` directory exists in this repo — no prior institutional learnings to carry forward.

### External References

- None — all patterns are local. The codebase has the exact functions being fixed, and the prior fix plan documents the architectural rationale.

---

## Key Technical Decisions

- **Exclusion list over stricter positive match:** Add a non-target location exclusion list (US, UK, Canada, Argentina, India, LATAM, APAC) that gates the `country_hint` fallback, rather than requiring the job title to explicitly contain "Germany"/"Spain". The exclusion approach is lower-risk — it only blocks jobs that are clearly wrong without changing the acceptance criteria for jobs that are probably right but lack an explicit country name.
- **Text-signal remote fallback, not domain-trust:** For remote `country_hint`, accept the job when no non-target signal is present (the exclusion list from U1). Domain-trust (checking if the URL domain is a known remote board) is deferred because it requires restructuring `infer_location`'s signature. The text-signal approach is a one-block change that ships with U1's exclusion list.
- **Wildcard patterns over subdomain-specific entries:** Add `r"liveblog365\.com"` (not `r"hirequorum\.liveblog365\.com"`) and `r"likesyou\.org"` to `skip_patterns` to catch all subdomains. This is a pure addition — no existing patterns are removed.
- **Numeric-ID guard at slug extraction, not post-hoc:** Skip all-digit slug segments in `extract_company_from_url()` rather than adding a post-hoc `re.match(r'^\d+$')` check after all extraction methods converge. Catching it at extraction prevents the numeric token from polluting subsequent fallback stages.
- **Test-first execution posture:** Every behavior-changing unit (U1-U4) writes its failing tests before implementation. Existing tests (195) must pass before marking any unit complete. U6 fills coverage gaps after all fixes land.

---

## Implementation Units

### U1. Add non-target location exclusion list to `infer_location()`

**Goal:** Reject jobs from non-EU locations that currently pass through the `country_hint` fallback.

**Requirements:** R1

**Dependencies:** None

**Files:**

- Modify: `scripts/discover_jobs.py` (`infer_location` function)
- Create: `tests/test_discover_jobs.py`

**Approach:**

- Add a `non_target_signals` list in `infer_location()` — cities and country names that are clearly outside DE/ES/EU-remote (e.g., "united states", "usa", "new york", "london", "uk", "canada", "toronto", "argentina", "buenos aires", "india", "mumbai", "bangalore", "singapore", "australia", "sydney", "japan", "tokyo", "mexico", "brazil", "são paulo", "latam", "apac")
- Check `text = (title + " " + url).lower()` against this list **before** the `country_hint` fallback
- If any non-target signal matches, return `(None, None)` regardless of `country_hint`
- The exclusion list sits between the EU-remote signal check and the country_hint fallback, so the data flow becomes: DE cities → ES cities → EU-remote signals → **non-target exclusion** → country_hint fallback → reject

**Execution note:** Write failing tests first — `test_infer_location_de_hint_with_us_city_returns_none`, `test_infer_location_de_hint_with_uk_city_returns_none`, `test_infer_location_es_hint_with_argentina_returns_none`. Then implement the exclusion list. Verify all 195 existing tests still pass.

**Patterns to follow:**

- Existing `infer_location()` structure — the DE/ES city whitelist lists at lines 237-257
- The EU-remote signal check at lines 258-269

**Test scenarios:**

- **Happy path:** DE-targeted query result with "London" in title → `infer_location` returns `(None, None)`
- **Happy path:** DE-targeted query result with "New York" in URL → `infer_location` returns `(None, None)`
- **Happy path:** ES-targeted query result with "Argentina" in title → `infer_location` returns `(None, None)`
- **Happy path:** DE-targeted query result with "Canada" in URL → `infer_location` returns `(None, None)`
- **Edge case:** DE-targeted query result with "Berlin" in title → still returns `("Berlin", "de")` (exclusion list does not interfere with valid matches)
- **Edge case:** ES-targeted query result with "Barcelona" in title → still returns `("Barcelona", "es")`
- **Edge case:** Remote-targeted query with "United States" in URL → returns `(None, None)` (exclusion fires before remote fallback — U3)
- **Error path:** Non-target signal present but city also matches (e.g., "Berlin, NH" or a company named "London Systems GmbH") — exclusion SHOULD fire (the city whitelist already matched and returns before the exclusion check; exclusion only gates the fallback)

**Verification:**

- `pytest tests/test_discover_jobs.py -v` passes
- `pytest tests/ -v` — all 195+ existing tests still pass
- Running `python scripts/discover_jobs.py --mode 24h --queries 5` produces zero jobs with US/UK/Argentina locations tagged as DE/ES

---

### U2. Block all scraper-farm subdomains in `skip_patterns`

**Goal:** Block `*.liveblog365.com` and `likesyou.org` from producing accepted jobs.

**Requirements:** R3

**Dependencies:** None

**Files:**

- Modify: `scripts/discover_jobs.py` (`skip_patterns` list in `result_to_job`)
- Modify: `tests/test_discover_jobs.py` (extend)

**Approach:**

- Add `r"liveblog365\.com"` to catch all subdomains (halvolink, hirequill, 2.halvolink, etc.) — the existing `r"hirequorum\.liveblog365\.com"` entry stays, so the older entry provides defense-in-depth
- Add `r"likesyou\.org"` to catch `careernest.likesyou.org` and any future subdomains
- These are pure additions — no existing patterns are removed or changed

**Execution note:** Write failing tests first — `test_result_to_job_skips_liveblog365_subdomain`, `test_result_to_job_skips_likesyou_org`. Then add the patterns. Verify all existing tests still pass.

**Patterns to follow:**

- Existing `skip_patterns` entries — raw regex strings applied via `re.search(pat, url_lower)` at line ~500
- Existing scraper-farm entries: `r"hirequorum\.liveblog365\.com"`, `r"wfh\.hstn\.me"`, `r"zerogtalent"`, etc.

**Test scenarios:**

- **Happy path:** URL `https://halvolink.liveblog365.com/job/12345` → `result_to_job` returns `None`
- **Happy path:** URL `https://hirequill.liveblog365.com/job/67890` → `result_to_job` returns `None`
- **Happy path:** URL `https://careernest.likesyou.org/remote-jobs/pm` → `result_to_job` returns `None`
- **Happy path:** URL `https://foo.liveblog365.com/some-path` → `result_to_job` returns `None` (wildcard catches novel subdomain)
- **Edge case:** URL `https://not-liveblog365.com/job/123` → should NOT be blocked (false positive guard)

**Verification:**

- `pytest tests/test_discover_jobs.py -v` passes
- `pytest tests/ -v` — all 195+ existing tests still pass
- Running discovery produces zero jobs from `liveblog365.com` or `likesyou.org` domains

---

### U3. Add remote `country_hint` fallback to `infer_location()`

**Goal:** Allow remote-targeted queries (country_hint="remote") to accept jobs as remote when no non-target signal is present.

**Requirements:** R2

**Dependencies:** U1 (the non-target exclusion list must exist so remote fallback does not accept non-EU remote jobs)

**Files:**

- Modify: `scripts/discover_jobs.py` (`infer_location` function)
- Modify: `tests/test_discover_jobs.py` (extend)

**Approach:**

- After the EU-remote signal check (step 3 in `infer_location`) and before the generic reject at `return (None, None)`, add a `country_hint == "remote"` check
- When `country_hint == "remote"` and the non-target exclusion list (U1) found no match, return `("Remote", "remote")`
- The data flow becomes: DE cities → ES cities → EU-remote signals → non-target exclusion → **remote fallback** → country_hint "de"/"es" fallback → reject
- Remote fallback fires before the "de"/"es" fallbacks, so a remote-targeted query that happens to contain a DE city (e.g., "Senior PM Remote Berlin") still gets the city match first (step 1), not the remote fallback — which is correct behavior

**Execution note:** Write failing tests first — `test_infer_location_remote_hint_with_no_signal_returns_remote`, `test_infer_location_remote_hint_with_us_signal_returns_none` (U1 exclusion fires first). Then implement the fallback. Verify all existing tests still pass.

**Patterns to follow:**

- Existing `country_hint` fallback pattern at lines 272-276 — same shape, adds "remote" case

**Test scenarios:**

- **Happy path:** Remote-targeted query result with title "Senior Product Manager" and no location signal → `infer_location` returns `("Remote", "remote")`
- **Happy path:** Remote-targeted query result from himalayas.app with title "Sr PM" → `infer_location` returns `("Remote", "remote")`
- **Happy path:** Remote-targeted query result from weworkremotely.com → `infer_location` returns `("Remote", "remote")`
- **Edge case:** Remote-targeted query with "United States" in URL → U1 exclusion fires first → returns `(None, None)` (remote fallback is not reached)
- **Edge case:** Remote-targeted query with "Berlin" in title → DE city whitelist matches first → returns `("Berlin", "de")` (remote fallback is not reached — correct: this is a city-specific remote role)
- **Edge case:** Remote-targeted query with "remote europe" in title → EU-remote signal matches first → returns `("Remote", "remote")` (remote fallback is not reached — correct: the explicit signal takes precedence)
- **Integration:** A full `result_to_job()` call with `country_hint="remote"` and a valid remote job → returns a dict with `country: "remote"` and `location: "Remote"`

**Verification:**

- `pytest tests/test_discover_jobs.py -v` passes
- `pytest tests/ -v` — all 195+ existing tests still pass
- Running discovery with remote-targeted queries produces jobs with `country: "remote"` in the output

---

### U4. Add numeric-ID guard in company name extraction

**Goal:** Prevent numeric-only slugs from being extracted as company names. Skip any all-digit token in the `/job/` slug path, regardless of length.

**Requirements:** R4

**Dependencies:** None

**Files:**

- Modify: `scripts/discover_jobs.py` (`extract_company_from_url` function)
- Modify: `tests/test_discover_jobs.py` (extend)

**Approach:**

- In `extract_company_from_url()` path 3 (the `/job/` slug extraction at line ~357), after `parts = slug.split("-")`, add a check: if the first token `parts[0]` is all digits (at any length), skip it and continue collecting from the next token
- If all tokens are either numeric or title words, return `""` (forcing the fallback chain to `extract_company_from_title` and then `extract_company_from_domain`)
- This is a guard at the extraction point — not a post-hoc filter — so the bad value never pollutes the company name variable

**Execution note:** Write failing tests first — `test_extract_company_from_url_numeric_slug_returns_empty`, `test_extract_company_from_url_numeric_slug_with_company_name_after`. Then implement the guard. Verify all existing tests still pass.

**Patterns to follow:**

- Existing `title_words` set at lines 363-371 — same pattern of checking tokens against a known set
- The dash-split logic at lines 372-377

**Test scenarios:**

- **Happy path:** URL `https://remoteok.com/job/2657353` → `extract_company_from_url` returns `""` (numeric slug, falls through)
- **Happy path:** URL `https://2.halvolink.liveblog365.com/job/2680134` → `extract_company_from_url` returns `""` (but the job will also be blocked by U2's skip_patterns)
- **Happy path:** URL `https://careers.playstation.com/senior-product-manager/job/6006519004` → `extract_company_from_url` returns `""` (falls through to `extract_company_from_domain` which extracts "Playstation" from the subdomain)
- **Edge case:** URL `https://example.com/job/42-senior-product-manager` → token "42" is < 4 digits, should probably still be skipped (numeric at any length). Guard should use `p.isdigit()` not length-based
- **Edge case:** URL `https://example.com/job/company-123-senior-pm` → token "company" is not numeric → extracted as company name as before (no regression)
- **Integration:** A full `result_to_job()` call with a URL like `https://halvolink.liveblog365.com/job/2657353` → blocked by U2 skip_patterns before U4's numeric guard is even reached — U4 is defensive for URLs that bypass U2

**Verification:**

- `pytest tests/test_discover_jobs.py -v` passes
- `pytest tests/ -v` — all 195+ existing tests still pass
- Running discovery produces zero company names that are pure numeric strings

---

### U5. Add 8-10 Spain-targeted queries to the query catalog

**Goal:** Rebalance the DE:ES query ratio from 33:13 toward parity.

**Requirements:** R5

**Dependencies:** None

**Files:**

- Modify: `scripts/discover_jobs.py` (`QUERY_CATALOG` list)

**Approach:**

- Add 8-10 new ES queries distributed across growth, AI, and generalist role types
- Use the same query patterns as existing ES entries (semantic, no `site:` operators)
- Target Spanish-language queries alongside English ones to catch companies that post only in Spanish
- Append to the end of the existing catalog to preserve ordering

**Test expectation:** none — query catalog addition. The existing `test_discover_script_runs_dry` and `test_discover_accepts_7d_mode` tests validate the catalog is loadable. U6 adds characterization coverage for catalog structure.

**Patterns to follow:**

- Existing ES queries at lines 76-78, 93-94, 108-110, 115, 130

**Verification:**

- `python scripts/discover_jobs.py --help` runs without error (catalog is syntactically valid)
- `pytest tests/ -v` — all existing tests pass
- Manual review: at least 20 ES queries in the catalog after this unit

---

### U6. Add regression test coverage for filtering functions

**Goal:** Ensure the classification functions have comprehensive test coverage beyond the specific bugs fixed in U1-U4.

**Requirements:** R6, R7

**Dependencies:** U1, U2, U3, U4, U5 (all fixes must be in place before characterization coverage is meaningful)

**Files:**

- Modify: `tests/test_discover_jobs.py` (extend with comprehensive coverage)

**Approach:**

- Add tests for `clean_company_name()` — empty string, company with suffix, company with location suffix
- Add tests for `extract_company_from_domain()` — known job board returns empty, unknown domain returns cleaned name
- Add tests for `extract_company_from_title()` — "at Company" pattern, "bei Company" pattern, no match
- Add tests for `infer_source()` — LinkedIn URL → "linkedin", StepStone URL → "stepstone", unknown → expected_source fallback
- Add tests for `result_to_job()` pipeline integration — valid job passes all gates, job with short title rejected, job with excluded title signal rejected, job with news indicator rejected, job with clickbait pattern rejected, job with blocked URL pattern rejected
- Add tests for `clean_title()` — title with location suffix stripped, title with "at Company" suffix stripped
- Use the same `monkeypatch` + `tmp_path` pattern from `TestJobsHubDiscover` for any file I/O tests
- Use direct function calls (no mocking needed for pure functions like `infer_location`, `clean_company_name`, etc.)

**Execution note:** These are characterization coverage tests — they document and lock in the current behavior of functions that were previously untested. Write them after U1-U4 fixes are complete so they cover the fixed behavior, not the buggy behavior.

**Patterns to follow:**

- `tests/test_tracker.py` `TestJobsHubDiscover` class — `monkeypatch` with `tmp_path`, direct function imports from `scripts.discover_jobs`

**Test scenarios:**

- **Happy path:** `clean_company_name("Acme Corp GmbH")` → `"Acme Corp"`
- **Happy path:** `clean_company_name("Acme Corp - Berlin")` → `"Acme Corp"`
- **Happy path:** `extract_company_from_domain("https://linkedin.com/jobs/123")` → `""` (known job board)
- **Happy path:** `extract_company_from_domain("https://acme.com/careers")` → `"Acme"`
- **Happy path:** `extract_company_from_title("Senior PM at Acme Corp")` → `"Acme Corp"`
- **Happy path:** `extract_company_from_title("Senior PM bei Acme GmbH")` → `"Acme"`
- **Edge case:** `extract_company_from_title("Senior Product Manager")` → `""` (no company in title)
- **Happy path:** `infer_source("https://linkedin.com/jobs/view/123", "linkedin")` → `"linkedin"`
- **Happy path:** `infer_source("https://www.stepstone.de/jobs/123", "stepstone")` → `"stepstone"`
- **Happy path:** `infer_source("https://acme.com/careers/pm", "linkedin")` → `"company"` (careers in domain)
- **Happy path:** `result_to_job` with valid result dict → returns structured dict
- **Edge case:** `result_to_job` with title length < 12 → returns `None`
- **Edge case:** `result_to_job` with excluded title signal → returns `None`
- **Error path:** `result_to_job` with news indicator in title → returns `None`
- **Error path:** `result_to_job` with blocked URL pattern → returns `None`

**Verification:**

- `pytest tests/test_discover_jobs.py -v` — all tests pass, coverage of `infer_location`, `extract_company_from_url`, `clean_company_name`, `extract_company_from_domain`, `extract_company_from_title`, `infer_source`, `result_to_job`
- `pytest tests/ -v` — all 195+ existing tests still pass

---

## System-Wide Impact

- **Interaction graph:** `infer_location()` is called from `result_to_job()` (line ~578), which is called in a loop for each Exa result in `main()`. A change to `infer_location`'s return value propagates through `result_to_job`'s `if location is None or country is None: return None` gate (line ~582). No other callers.
- **Error propagation:** `infer_location()` returns `(None, None)` for rejection and `(str, str)` for acceptance. Both paths are handled cleanly by `result_to_job()`. New rejection paths (non-target exclusion, remote fallback) use the same `(None, None)` sentinel — no new error states.
- **State lifecycle risks:** None — all modified functions are pure (no side effects, no file I/O). The only stateful component is the `QUERY_CATALOG` list (U5), which is read-only at runtime.
- **API surface parity:** The tracker server's `/api/discover` endpoint runs `discover_jobs.py` as a subprocess and reads `job_queue.html` afterward. The output format (JS object notation) and field schema are unchanged — the tracker server needs no modification.
- **Integration coverage:** U2 and U4 interact — a URL blocked by U2's `skip_patterns` never reaches U4's numeric-ID guard. This is correct (defense in depth), but the test for U4 should use URLs that bypass `skip_patterns` to exercise the numeric guard in isolation.
- **Unchanged invariants:** The `result_to_job()` return type (`dict | None`), the JOBS array format in `data/job_queue.html`, the `exa_search()` function signature, and the `parse_existing_jobs()` / `deduplicate_jobs()` / `append_to_queue()` functions are all unchanged.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| DE-targeted query results with no city and no non-target signal will still be accepted as "Germany" (the country_hint fallback remains the last resort). This is acceptable — the exclusion list catches the clearly-wrong cases; borderline cases stay. | The exclusion list can be expanded if new misclassifications are observed. |
| The remote fallback (U3) may accept non-EU remote jobs that lack an explicit US/UK/India signal in title or URL (e.g., a remote job in Nigeria with no location text). The exclusion list cannot catch these. | This is an acceptable trade-off — the alternative (rejecting ALL remote jobs as today) is worse. Domain-trust is deferred to a future plan for this exact reason. |
| `extract_company_from_url()` may produce empty strings for legitimate numeric subdomain patterns (e.g., `123test.com`). | The numeric guard only fires on `/job/` slug extraction (path 3), not subdomain extraction (path 1). Legitimate subdomains are unaffected. |
| U3 depends on U1 — implementing U3 before U1 would open the floodgates to non-EU remote jobs. | Plan sequencing enforces U1 → U3. `ce-work` processes units in order. |

---

## Sources & References

- **Origin diagnosis:** Session analysis of June 28 discovery run output (`data/job_queue.html` — 30 jobs, 27 generic locations, 13 garbage company names, 0 remote)
- **Prior plan:** `docs/plans/2026-06-07-001-fix-discovery-returns-nothing-plan.md` — documented the Exa API migration and whitelist-only location strategy
- **Primary code:** `scripts/discover_jobs.py` (733 lines) — `infer_location()` at lines 237-277, `result_to_job()` at lines 431-580, `extract_company_from_url()` at lines 311-377, `skip_patterns` at lines 488-545, `QUERY_CATALOG` at lines 66-137
- **Existing tests:** `tests/test_tracker.py` — `TestJobsHubDiscover` (8 tests), `TestDiscoveryAsync` (4 tests)
- **Model review:** Kimi K2.6 — fix priority F2 → F4 → F1+F2 → F3 → F5 → F6; GLM-5.1 — fix priority F4 → F3 → F2 → F1 → F5
