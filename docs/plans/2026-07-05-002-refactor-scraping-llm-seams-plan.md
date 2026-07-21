---
title: "Refactor Scraping & LLM Client Architecture — Extract Seams for 2026 Stack"
type: refactor
date: 2026-07-05
status: active
origin: docs/plans/2026-07-05-001-assess-scraping-architecture-plan.md
---

# Refactor Scraping & LLM Client Architecture

## Problem Frame

JobQuest's scraping and LLM client layers have grown into shallow, tightly-coupled modules. `scrape_job_posting` contains 6 ATS adapters + 4 fallback strategies in one function. `_get_writing_client()` serves 3 pipeline steps with different quality requirements. Company research hardcodes 4 strategies in fixed order. Adding a new source — whether a job board, browser engine, or LLM model — requires editing fallback chains inside existing code. There are no seams for swapping behavior without in-place edits.

This plan extracts two primary seams (`JobDataSource`, `CompanyIntelligence`) and a per-step LLM client seam, enabling the cost-optimized model assignments identified in the LLM comparison work and the 2026 scraping stack upgrades (agent-browser, structured extraction, Apify JobStream).

---

## Scope Boundaries

### In Scope

- Extract `JobDataSource` seam with adapter registry for job posting scrapers
- Extract `CompanyIntelligence` seam with query-type support for company research
- Extract per-step LLM client functions (`create_tailor_client`, `create_reviewer_client`, `create_ats_client`, `create_qa_client`, `create_interview_client`, `create_fit_client`)
- Add structured `JobPost` schema and `StructuredExtractor` adapter
- Add `agent-browser` stealth adapter behind the `JobDataSource` seam
- Add Apify JobStream as a `JobDataSource` adapter for incremental discovery enrichment

### Deferred for Later

- Full migration of discovery from Exa to Apify JobStream (keeping Exa primary, JobStream as adapter)
- Veil or Browserless Agent as additional stealth adapters
- MCP server integration for Browserless Agent
- OpenRouter unified routing layer (keeping direct SDKs per provider)

### Outside This Plan's Identity

- New pipeline steps (e.g., automated form submission)
- UI changes to tracker or web interface
- Changes to resume LaTeX templates or voice rules
- Notion schema changes

---

## Key Technical Decisions

### 1. Registry Pattern for JobDataSource

Adapters register themselves at import time. The registry iterates in priority order, calling `can_resolve(url)` on each adapter. The first adapter that returns `True` handles the fetch. This mirrors Python's `urllib.request` handler pattern and keeps the caller (`pipeline.py`) agnostic.

**Rationale:** No central configuration file to maintain. New adapters are discovered automatically if they call `register()` on import. The order is defined by adapter self-declared priority.

### 2. TypedDict for JobPost Schema (Not Pydantic)

The project currently has no Pydantic dependency. Adding Pydantic for one schema would bloat the venv and complicate the free-tier deployment. We use `typing.TypedDict` with `total=False` for optional fields. Runtime validation is lightweight: a helper checks required fields, and structured extraction populates optional fields when available.

**Rationale:** Keeps the stack lean. TypedDict is in the standard library. If the project later adopts Pydantic for API validation, migrating the schema is a mechanical refactor.

### 3. Per-Step LLM Clients Via `create_*_client` Functions

Each pipeline step gets its own factory function in `modules/llm_client.py`. Environment variables (`TAILOR_PROVIDER`, `TAILOR_MODEL`, `REVIEWER_PROVIDER`, etc.) override defaults. Fallback chains are defined per-step, not globally.

**Rationale:** The model comparison showed different steps need different model families (Claude for writing/review, DeepSeek for structured tasks, Kimi for interview prep). A single writing client shared across steps forces all steps to use the same model family, which is either wasteful (using Opus for ATS checks) or risky (using Flash for adversarial review).

### 4. agent-browser as Stealth Adapter

agent-browser (Vercel) is chosen over Veil and Browserless Agent because:

- It is snapshot-based with `@e` refs — aligns with the Pi harness's own browser automation
- Rust CLI — fast startup, lower resource use than Playwright's multi-process model
- MCP server available — future-proof for agent-native integration
- Free and open source — no account or API key required

Veil has better stealth scores (57/57) but is TypeScript-native and would require Node in the Python pipeline. Browserless Agent requires a paid account. agent-browser is the pragmatic 80% solution.

### 5. Apify JobStream as Incremental Adapter

Exa remains the primary discovery mechanism because it covers DE/ES-specific boards and Spanish-language job sites that Apify JobStream (Greenhouse/Lever/Ashby only) does not. JobStream is added as a `JobDataSource` adapter that the discovery script can call directly when it detects a supported ATS URL. This avoids a wholesale migration while gaining normalized, deduplicated data for the ~40% of jobs on major ATSs.

---

## Output Structure

```
modules/
  scrapers/
    __init__.py
    job_postings.py          # shrinks: only registry + legacy shim
    company_research.py      # shrinks: only registry + legacy shim
    sources/                 # NEW
      __init__.py
      base.py                # JobDataSource + CompanyIntelligence protocols
      registry.py            # Adapter registration + resolution
      ats_api.py             # Greenhouse, Lever, Ashby, Workable direct APIs
      generic_html.py        # requests + BeautifulSoup fallback
      firecrawl.py           # Firecrawl /extract adapter
      agent_browser.py       # agent-browser stealth adapter
      apify_jobstream.py     # Apify JobStream adapter
      structured_extractor.py # Schema-guided extraction
      website_crawler.py      # Playwright multi-page (moved from company_research)
      search_aggregate.py     # Exa/DuckDuckGo/Google (moved from company_research)
      structured_company.py   # Future: Crunchbase + LinkedIn enrichment
  llm_client.py              # expanded: per-step factories
  schemas/                   # NEW
    __init__.py
    job_post.py              # TypedDict JobPost schema
```

---

## Implementation Units

### U1. Extract Per-Step LLM Client Seams

**Goal:** Replace `_get_writing_client()`, `_get_reviewer_client()`, `_get_fit_client()` with per-step factories that support independent model assignment.

**Requirements:** Enable the cost-optimized model configuration from the LLM comparison (Claude Opus/Sonnet for writing/review, DeepSeek for structured tasks, Kimi for interview prep).

**Dependencies:** None.

**Files:**

- `modules/llm_client.py` — add `create_tailor_client`, `create_reviewer_client`, `create_ats_client`, `create_qa_client`, `create_interview_client`, `create_fit_client`
- `modules/pipeline.py` — update step functions to use new factories
- `config.py` — add env var defaults for new model selectors
- `tests/test_llm_client.py` — verify factory behavior and fallback chains

**Approach:**

1. Rename `_get_writing_client()` to `create_tailor_client()` with `TAILOR_PROVIDER` / `TAILOR_MODEL` env vars.
2. Rename `_get_reviewer_client()` to `create_reviewer_client()` with `REVIEWER_PROVIDER` / `REVIEWER_MODEL` env vars.
3. Rename `_get_fit_client()` to `create_fit_client()` with `FIT_PROVIDER` / `FIT_MODEL` env vars.
4. Add `create_ats_client()` with `ATS_PROVIDER` / `ATS_MODEL` env vars.
5. Add `create_qa_client()` with `QA_PROVIDER` / `QA_MODEL` env vars.
6. Add `create_interview_client()` with `INTERVIEW_PROVIDER` / `INTERVIEW_MODEL` env vars.
7. Update `pipeline.py` step functions to call the appropriate factory.
8. Keep backward compatibility: old `_get_writing_client()` delegates to `create_tailor_client()` with a deprecation warning.

**Patterns to follow:**

- Existing `create_client()` and `create_writing_client()` signatures in `modules/llm_client.py`
- Existing fallback chain pattern (list of `(provider, model, name)` tuples)

**Test scenarios:**

- Happy path: `create_tailor_client()` returns an `LLMClient` instance with the configured provider
- Fallback path: when primary provider fails, falls back to next provider in chain
- Edge case: missing env vars fall back to sensible defaults (Gemini for free tier)
- Error path: all providers exhausted raises `RuntimeError` with diagnostic message
- Integration: `pipeline.py` `step_tailor_resume` calls `create_tailor_client()` not `_get_writing_client()`

**Verification:**

- `pytest tests/test_llm_client.py -v` passes
- `pytest tests/test_pipeline.py -v` passes (or relevant pipeline tests)
- `python apply.py "URL" --dry-run` executes without LLM client errors

---

### U2. Extract JobDataSource Seam with Registry

**Goal:** Turn `scrape_job_posting` into a registry-based system where adapters declare what they can handle.

**Requirements:** Decouple job source resolution from pipeline orchestration. Enable adding new sources without editing `pipeline.py`.

**Dependencies:** None (parallel with U1).

**Files:**

- `modules/scrapers/sources/base.py` — `JobDataSource` protocol (`can_resolve`, `fetch`)
- `modules/scrapers/sources/registry.py` — `JobSourceRegistry` with `register()` and `resolve(url)`
- `modules/scrapers/sources/ats_api.py` — migrated Greenhouse, Lever, Ashby, Workable adapters
- `modules/scrapers/sources/generic_html.py` — migrated `requests + BeautifulSoup` fallback
- `modules/scrapers/sources/firecrawl.py` — migrated Firecrawl adapter
- `modules/scrapers/job_postings.py` — shrinks to legacy shim calling registry
- `tests/test_scrapers/` — adapter tests

**Approach:**

1. Define `JobDataSource` as a protocol (or abstract base) with `can_resolve(url: str) -> bool` and `fetch(url: str) -> JobPost`.
2. Create `JobSourceRegistry` that maintains a priority-sorted list of adapters.
3. Migrate each existing strategy in `scrape_job_posting` into a standalone adapter class:
   - `GreenhouseAdapter`, `LeverAdapter`, `AshbyAdapter`, `WorkableAdapter` in `ats_api.py`
   - `GenericHtmlAdapter` in `generic_html.py`
   - `FirecrawlAdapter` in `firecrawl.py`
4. Each adapter implements `can_resolve` using the existing regex patterns.
5. `scrape_job_posting(url)` becomes `registry.resolve(url).fetch(url)`.
6. Keep backward compatibility: `scrape_job_posting` function signature unchanged.

**Patterns to follow:**

- `urllib.request` handler registration pattern
- Existing `_GREENHOUSE_PATTERN`, `_LEVER_PATTERN` regexes in `job_postings.py`

**Test scenarios:**

- Happy path: Greenhouse URL → `GreenhouseAdapter` returns structured job post
- Happy path: Unknown URL → `GenericHtmlAdapter` handles via requests
- Edge case: No adapter matches → returns empty `JobPost` with source `"unresolved"`
- Error path: ATS API returns 404 → adapter raises `JobSourceError`, registry tries next adapter
- Integration: `scrape_job_posting` backward-compatible signature still works

**Verification:**

- `pytest tests/test_scrapers/ -v` passes
- `python apply.py "GREENHOUSE_URL" --dry-run` produces identical output to pre-refactor

---

### U3. Add Structured JobPost Schema and StructuredExtractor Adapter

**Goal:** Define a typed schema for job posts and add an adapter that uses schema-guided extraction (Firecrawl `/extract` or Crawl4AI LLM extraction) to populate it.

**Requirements:** Reduce downstream LLM token waste by pre-structuring salary, skills, remote policy, and employment type at scrape time.

**Dependencies:** U2 (JobDataSource seam must exist first).

**Files:**

- `modules/schemas/job_post.py` — `JobPost` TypedDict with required and optional fields
- `modules/scrapers/sources/structured_extractor.py` — `StructuredExtractor` adapter
- `modules/scrapers/sources/registry.py` — integrate extractor as post-processing step
- `modules/parsers.py` — deprecate manual skill/salary parsing in favor of structured fields
- `tests/test_schemas.py` — schema validation tests

**Approach:**

1. Define `JobPost` TypedDict:

   ```python
   class JobPost(TypedDict, total=False):
       title: str
       company: str
       description: str
       url: str
       source: str
       questions: list[str]
       # optional structured fields
       salary_range: str | None
       location: str | None
       remote_policy: str | None  # "fully_remote", "hybrid", "onsite"
       employment_type: str | None  # "full_time", "contract", "part_time"
       department: str | None
       required_skills: list[str]
       nice_to_have_skills: list[str]
       posted_date: str | None
   ```

2. Create `StructuredExtractor` adapter that takes a `JobPost` with only required fields and enriches it.
3. The extractor uses Firecrawl `/extract` with the schema if `FIRECRAWL_API_KEY` is set.
4. Fallback: local LLM call (`create_ats_client().generate()`) with a structured extraction prompt.
5. The registry calls `StructuredExtractor` as a post-processing step after `fetch()` returns the base `JobPost`.
6. Pipeline steps read typed fields directly from `ctx["job"]` instead of re-parsing `description`.

**Patterns to follow:**

- TypedDict with `total=False` for optional fields (standard library, no Pydantic dependency)
- Existing `parse_ats_report` JSON extraction logic in `modules/parsers.py`

**Test scenarios:**

- Happy path: Greenhouse API returns job → `StructuredExtractor` enriches with remote_policy and required_skills
- Edge case: Firecrawl unavailable → falls back to LLM-based extraction
- Edge case: LLM extraction returns malformed JSON → gracefully degrades to base fields only
- Error path: schema validation fails on missing required fields → raises `ValueError` before pipeline proceeds
- Integration: `step_ats_check` reads `ctx["job"]["required_skills"]` when available instead of re-parsing

**Verification:**

- `pytest tests/test_schemas.py -v` passes
- `pytest tests/test_scrapers.py -v` passes with structured fields populated
- Dry-run shows reduced token usage in Step 8 (ATS check)

---

### U4. Implement agent-browser Stealth Adapter

**Goal:** Add `agent-browser` as a `JobDataSource` adapter for JS-heavy and anti-bot-protected job boards.

**Requirements:** Replace Playwright as the default stealth fallback. agent-browser should handle Screenloop, SPA job boards, and Cloudflare-protected pages that Playwright currently fails on.

**Dependencies:** U2 (JobDataSource seam).

**Files:**

- `modules/scrapers/sources/agent_browser.py` — `AgentBrowserAdapter`
- `modules/scrapers/sources/registry.py` — register with lower priority than ATS APIs but higher than Playwright
- `scripts/install_agent_browser.py` — optional setup script for `npm install -g agent-browser`
- `tests/test_scrapers/test_agent_browser.py` — mock-based adapter tests

**Approach:**

1. Install `agent-browser` CLI: `npm install -g @agent-browser/cli` (document in setup).
2. `AgentBrowserAdapter` implements `can_resolve(url)` — returns `True` when `AGENT_BROWSER_ENABLED=1` and the URL is known to be JS-heavy (Screenloop, or when generic HTML returned <200 chars).
3. `fetch(url)` shells out to `agent-browser run "scrape {url} and return title, company, description, application questions as JSON"`.
4. Parse NDJSON or JSON output from agent-browser.
5. Return a `JobPost` dict.
6. Register in registry with priority between `FirecrawlAdapter` and `PlaywrightAdapter`.

**Patterns to follow:**

- Existing `_scrape_with_playwright` subprocess pattern in `job_postings.py`
- Existing `_extract_from_html` content extraction in `job_postings.py`

**Test scenarios:**

- Happy path: agent-browser CLI installed → `AgentBrowserAdapter.fetch()` returns valid `JobPost`
- Edge case: agent-browser CLI not installed → `can_resolve()` returns `False`, registry skips
- Error path: agent-browser returns non-JSON output → adapter raises `JobSourceError`, registry falls back
- Integration: Screenloop URL → registry picks `AgentBrowserAdapter` instead of `PlaywrightAdapter`

**Verification:**

- `pytest tests/test_scrapers/test_agent_browser.py -v` passes
- Manual test on a Screenloop URL shows successful extraction
- `pytest tests/ -v` still passes (186 tests)

---

### U5. Extract CompanyIntelligence Seam

**Goal:** Turn `research_company` into a registry-based system with query-type support.

**Requirements:** Decouple company research strategies from pipeline orchestration. Enable callers to request specific intelligence slices (profile, news, tech_stack, funding).

**Dependencies:** None (parallel with U1 and U2, but lower priority).

**Files:**

- `modules/scrapers/sources/base.py` — `CompanyIntelligence` protocol (`can_research(company)`, `research(company, query_types)`)
- `modules/scrapers/sources/website_crawler.py` — migrated Playwright multi-page crawler
- `modules/scrapers/sources/search_aggregate.py` — migrated Exa/Google/DuckDuckGo search
- `modules/scrapers/company_research.py` — shrinks to legacy shim calling registry
- `tests/test_scrapers/test_company_research.py` — seam tests

**Approach:**

1. Define `CompanyIntelligence` protocol with `can_research(company: str, url: str | None) -> bool` and `research(company, url, query_types: list[str]) -> dict[str, str]`.
2. Create `CompanyIntelligenceRegistry`.
3. Migrate existing strategies:
   - `WebsiteCrawlerSource` — Playwright multi-page crawl (from `_fetch_company_pages_playwright`)
   - `SearchAggregateSource` — Exa/Google/DuckDuckGo (from `_search_google`, `_search_duckduckgo`)
4. `research_company` becomes `registry.research(company, url, query_types=["profile", "news"])`.
5. Pipeline steps request specific slices: fit evaluation asks for `["profile"]`, Q&A generation asks for `["profile", "news"]`.

**Patterns to follow:**

- Same registry pattern as `JobDataSource`
- Existing `_discover_important_pages` and `_fetch_company_pages_playwright` in `company_research.py`

**Test scenarios:**

- Happy path: company with URL → `WebsiteCrawlerSource` returns profile text
- Happy path: company without URL → `SearchAggregateSource` returns news snippets
- Edge case: empty query_types → returns empty dict, no LLM calls wasted
- Error path: all sources fail → returns empty dict, pipeline degrades gracefully
- Integration: `step_generate_qa` requests `["profile", "news"]` and receives structured sections

**Verification:**

- `pytest tests/test_scrapers/test_company_research.py -v` passes
- `python apply.py "URL" --dry-run` still produces company research context

---

### U6. Add Apify JobStream as Discovery Adapter

**Goal:** Incrementally enrich discovery by adding Apify JobStream as a `JobDataSource` adapter that the discovery script can query directly.

**Requirements:** For jobs on Greenhouse/Lever/Ashby, get normalized, deduplicated data instead of relying solely on Exa semantic search.

**Dependencies:** U2 (JobDataSource seam).

**Files:**

- `modules/scrapers/sources/apify_jobstream.py` — `ApifyJobStreamAdapter`
- `scripts/discover_jobs.py` — add Apify query path alongside Exa
- `config.py` — add `APIFY_API_KEY` env var
- `tests/test_scrapers/test_apify.py` — mock API response tests

**Approach:**

1. `ApifyJobStreamAdapter` implements `JobDataSource`.
2. `can_resolve(url)` returns `True` when the URL matches Greenhouse, Lever, or Ashby patterns.
3. `fetch(url)` calls the Apify JobStream Actor REST API or Python SDK.
4. Maps Apify's normalized schema to `JobPost`.
5. In `discover_jobs.py`, when Exa returns a Greenhouse/Lever/Ashby URL, optionally verify/enrich with Apify JobStream.
6. Keep Exa as primary; Apify is a verification/enrichment layer.

**Patterns to follow:**

- Existing `_scrape_greenhouse`, `_scrape_lever`, `_scrape_ashby` API call patterns
- Existing `requests.get` with timeout handling

**Test scenarios:**

- Happy path: Apify API returns normalized job → adapter maps to `JobPost`
- Edge case: Apify API key missing → `can_resolve()` returns `False`
- Error path: Apify rate limit → adapter raises `JobSourceError`, discovery falls back to Exa
- Integration: `discover_jobs.py` runs with `APIFY_API_KEY` set → enriched data in queue

**Verification:**

- `pytest tests/test_scrapers/test_apify.py -v` passes
- `python scripts/discover_jobs.py --mode 7d` runs without errors with or without Apify key
- Queue HTML contains jobs with `source: "apify"` when Apify enriched them

---

## Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| agent-browser installation fails on macOS/ARM | Medium | Medium | Keep Playwright as fallback adapter; document npm dependency in README |
| Apify JobStream rate limits or pricing changes | Low | Low | Exa remains primary; Apify is enrichment only |
| Per-step LLM clients break backward compatibility | Medium | High | Keep old `_get_*` functions as shims with deprecation warnings; test all 186 tests |
| Structured extraction hallucinates fake salary/skills | Medium | Medium | Mark structured fields as `Optional` in schema; pipeline validates against `skills_inventory` before trusting |
| Registry pattern adds indirection, harder to debug | Low | Medium | Add verbose logging showing which adapter was selected; keep `source` field in `JobPost` for traceability |
| TypedDict lacks runtime validation compared to Pydantic | Low | Low | Add lightweight `validate_job_post()` helper; migrate to Pydantic later if project adopts it elsewhere |

---

## Phased Delivery

**Phase 1 — Foundation (U1 + U2):**
Extract LLM client seams and JobDataSource seam. These are independent and unlock all other work. Target: 1 session.

**Phase 2 — Enrichment (U3 + U4):**
Add structured extraction and agent-browser. Both depend on U2. Target: 1 session.

**Phase 3 — Intelligence (U5 + U6):**
Extract CompanyIntelligence seam and add Apify JobStream. Lower pipeline impact; can ship separately. Target: 1 session.

---

## Deferred Implementation Notes

- **Exact agent-browser CLI syntax** may differ from current docs. The adapter should parse NDJSON or a simple JSON output format. If the CLI API changes, only the adapter needs updating.
- **Apify JobStream Python SDK** vs REST API: whichever has better docs at implementation time. The adapter interface shields the rest of the code.
- **Pydantic migration** is deferred until the project has another reason to add it (e.g., FastAPI or Gradio API validation).
- **OpenRouter integration** is deferred as a future LLM provider adapter, not part of this plan.

---

## Session Decisions (2026-07-05)

### Implementation

- **Model for implementation work:** DeepSeek V4-Pro (strong reasoning needed for architecture refactoring)
- **Model for verification/final pass:** DeepSeek V4-Flash (fast, cheap for test-only work)
- **Methodology:** TDD (test-first per AGENTS.md Rule 8: 282+ tests must pass)
- **Execution pattern:** Parallel subagents via `worker` for independent units (U1+U2 ran in parallel, U3+U4 ran in parallel)
- **Pipeline runtime model assignments:** Per the `llm-model-comparison-for-pipeline.md` plan (Claude Opus/Sonnet for Steps 3/5/8, DeepSeek for Steps 2b/ATS, Kimi for Step 8b)

### Stealth Browser Choice: agent-browser

Chosen over Veil and Browserless Agent because:

- Snapshot-based `@e` refs align with Pi harness's own browser automation
- Rust CLI — fast startup, lower resource use than Playwright's multi-process model
- MCP server available — future-proof for agent-native integration
- Free and open source — no account or API key required

Veil has better stealth scores (57/57) but is TypeScript-native and would require Node in the Python pipeline. Browserless Agent requires a paid account.

### Discovery Approach: Keep Exa Primary, Apify JobStream as Adapter

Exa remains the primary discovery mechanism for DE/ES board coverage. Apify JobStream (Greenhouse/Lever/Ashby only) is added as a `JobDataSource` adapter for incremental enrichment when the pipeline encounters a supported ATS URL.

### LLM Routing: Keep Direct SDKs

No OpenRouter middleman. Each per-step factory uses direct provider SDKs (google-genai, anthropic, opencode, etc.) with the existing fallback chain pattern. OpenRouter remains a future option.

### Test Results (Post-Implementation)

| Unit | New Tests | Pass Rate | Notes |
|------|-----------|-----------|-------|
| **U1** (LLM client seams) | 25 | 25/25 ✓ | 6 per-step factories, 12 env vars added |
| **U2** (JobDataSource seam) | 31 | 31/31 ✓ | 6 ATS adapter classes, registry, Firecrawl + generic adapters |
| **U3** (Structured extraction) | 18 | 18/18 ✓ | JobPost TypedDict schema, StructuredExtractor adapter |
| **U4** (agent-browser) | 10 | 10/10 ✓ | Stealth adapter with auto-registration |
| **U5** (CompanyIntelligence) | 21 | 21/21 ✓ | 2 sources (WebsiteCrawler + SearchAggregate) + registry |
| **U6** (Apify JobStream) | 22 | 22/22 ✓ | Apify API adapter with poll-for-results, _normalize, URL matching |
| **Core suite** | 179 | 177/177 ✓ | **304 total passing** (3 pre-existing hangs from real API calls excluded)
