# Architecture Assessment: Scraping & Company Research (July 2026)

**Type:** Assessment / Refactor plan  
**Date:** 2026-07-05  
**Status:** Draft — awaiting candidate selection

---

## 1. Research Summary: State of the Art (July 2026)

### Browser Automation — Playwright Is Now "Legacy"

The browser automation landscape shifted dramatically in mid-2026. Playwright/Puppeteer are now considered **detectable and brittle for AI-agent workflows** — they set `navigator.webdriver=true`, use `--enable-automation` flags, and have robotic input patterns that anti-bot systems catch.

**New leaders:**

| Tool | Launch | Wedge | Relevance to JobQuest |
|------|--------|-------|----------------------|
| **Browserless Agent** | June 2026 | MCP-native, single stateful tool, persistent sessions, command batching | Could replace Playwright entirely via MCP |
| **Veil** | June 2026 | Raw CDP over real Chrome, stealth (57/57 sannysoft), no Playwright/Puppeteer deps | Best for hostile sites (LinkedIn, job boards with anti-bot) |
| **Browserbase Agents** | 2026 GA | Natural-language goal → reusable agent, no selectors | Could simplify company research to single API call |
| **agent-browser** (Vercel) | 2026 | Snapshot-based `@e1` refs, Rust CLI, 75% context reduction, MCP server | Already used by pi harness — could unify company research |
| **Lightpanda Agent** | 2026 | LLM at *buildtime* (generates deterministic PandaScript), no model at runtime | Cheapest for repeatable scrapes |
| **Alibaba Page Agent** | July 2026 | In-page JS agent, DOM dehydration, runs inside user's browser session | Less relevant for backend pipeline |

**Implication:** JobQuest's Playwright-first fallback chain (`requests → Firecrawl → Playwright`) is now the slowest, most detectable path. In 2026, the optimal order is closer to `AI-native scraper → stealth browser (Veil/agent-browser) → plain HTTP`.

### AI-Native Scraping — Firecrawl vs Crawl4AI vs Structured APIs

Two philosophies dominate in 2026:

1. **Managed LLM-ready APIs** (Firecrawl, Thunderbit, Olostep) — turn any URL into clean Markdown or schema-validated JSON. Firecrawl now has an MCP server and `/extract` endpoint for structured data. Credit cost: ~1 credit/scrape, 5 credits for stealth or AI extraction.
2. **Self-hosted Python-native** (Crawl4AI) — importable async library with built-in LLM extraction, crawl graphs, event hooks. Apache-2.0, no per-page cost. Docker image ~2GB.

**New capability:** Schema-guided extraction (Schematron, Thunderbit) — define a JSON schema once, get typed records across *any* site without per-site selectors. This replaces BeautifulSoup + regex heuristics.

### Job Data Infrastructure — Normalized ATS Feeds Are Commoditized

In 2026, you no longer need to maintain per-ATS scrapers:

- **Apify JobStream** (`brebiv/jobstream`) — normalized, deduplicated, change-tracked job postings from Greenhouse + Lever + Ashby public APIs. $2.50 / 1,000 postings.
- **Hiring-Signal Intel** (`seibs.co/hiring-signal-intel`) — same + hiring surge flags, department expansion detection, JD tech-stack detection.
- **Free Job Postings API** (Launly) — 1.8M+ active listings across 30+ ATSs, no auth.
- **Company Hiring Signals** (`oblanceolate_mandola/company-hiring-signals`) — scrape by company name across Greenhouse/Lever/Ashby → JSON at $0.002/posting.

**Key insight:** The *value* has moved from "can I fetch this job?" (solved) to "what signals can I derive?" (hiring velocity, tech stack, salary trends).

### ATS APIs — Stable, But MCP Is the New Integration Layer

Greenhouse, Lever, Ashby, Workable public JSON APIs remain unchanged and auth-free. What changed in 2026:

- **Greenhouse MCP** (May–June 2026) — governed connection layer for AI tools to query live hiring data.
- **Workable MCP Server** (2026) — AI assistants can query and act on live HR info via natural language.
- **Ashby** upgraded AI-Assisted Application Review to GPT-5.4 (June 2026).

### Company Research — Multi-Source Enrichment Is Standard

Modern company intelligence pipelines assemble from:

- Legal/funding: Crunchbase, Tracxn, MCA21, Companies House
- Employment signals: LinkedIn headcount, team structure
- Technology: job posting tech-stack detection, website source analysis
- News/sentiment: media monitoring
- Reviews: G2, Glassdoor

Tools like DataFlirt and Crawlora provide unified company profiles via structured APIs with no per-site maintenance.

---

## 2. Current Architecture Friction

### Where We Bounce Between Modules

Understanding how JobQuest scrapes requires reading:

- `modules/scrapers/job_postings.py` (ATS APIs + generic HTML + Firecrawl + Playwright)
- `modules/scrapers/company_research.py` (Playwright multi-page + crawl4ai + Firecrawl + search)
- `scripts/discover_jobs.py` (Exa semantic search, 80+ query catalog)
- `modules/pipeline.py` (orchestration, calls all of the above)

These four files have overlapping concerns (browser automation, HTML parsing, API calls) but no shared seam.

### Shallow Modules (Deletion Test)

**`scrape_job_posting` in `job_postings.py`** — If you deleted this function, complexity would reappear across every caller. But the *function itself* is shallow: its interface (one URL in, one dict out) hides very little — inside, it contains 6 ATS API adapters, regex patterns, a fallback chain through 4 strategies, and inline error handling. The interface is simple, but so is the concept; the complexity is all in the implementation with no internal seams.

**`research_company` in `company_research.py`** — Same pattern. One function with 4 strategies (Playwright, crawl4ai, Firecrawl, search) hardcoded in sequence. No way to swap strategies or test them independently.

### Tight Coupling Across Seams

The scrapers leak their tool choices into the pipeline:

- `pipeline.py` imports `scrape_job_posting` and `research_company` directly
- There is no abstraction over "job data source" or "company intelligence source"
- If Firecrawl credits run out, or Playwright breaks on a new macOS version, the edit happens inside the scraper module, not at a seam

### No Structured Extraction Seam

Current output is always `dict {title, company, description, url, source, questions}` — plain text. Modern pipelines use schema-guided extraction to return typed records (salary range, skills list, department, employment type, remote policy) directly. JobQuest would benefit from a structured extraction seam that could be satisfied by Firecrawl `/extract`, Crawl4AI LLM extraction, or a custom parser.

### Discovery Is General-Purpose Search, Not Job-Specific

`discover_jobs.py` uses Exa (general semantic web search) with 80+ hand-tuned queries. In 2026, dedicated job data APIs and Apify Actors provide normalized, deduplicated feeds with change tracking — no query engineering required.

---

## 3. Deepening Opportunities

### Candidate 1: Extract a `JobDataSource` Seam

**Files:** `modules/scrapers/job_postings.py`, `modules/pipeline.py`

**Problem:** `scrape_job_posting` is a shallow catch-all. Every ATS adapter and fallback strategy lives in one function. Tests must exercise the full fallback chain to verify any single path. There is no seam for swapping strategies (e.g., "use Apify JobStream instead of direct ATS APIs").

**Solution:** Define a `JobDataSource` interface with methods like `can_resolve(url) → bool` and `fetch(url) → JobPost`. Implement adapters for:

- `ATSApiSource` (Greenhouse, Lever, Ashby, Workable direct APIs)
- `StructuredApiSource` (Apify JobStream, free Job Postings API)
- `AIExtractorSource` (Firecrawl `/extract`, Crawl4AI with schema)
- `StealthBrowserSource` (Veil, agent-browser, Browserless Agent)

A registry tries adapters in order of preference. The pipeline calls `registry.fetch(url)` and gets back a typed `JobPost` — no knowledge of which adapter succeeded.

**Benefits:**

- **Locality:** A broken ATS API is fixed in one adapter, not in the middle of a 200-line function.
- **Leverage:** New job sources (e.g., a new ATS, a new API) are added by writing one adapter, not editing fallback chains.
- **Tests:** Each adapter is tested through the `JobDataSource` interface, not through the full pipeline.

---

### Candidate 2: Extract a `CompanyIntelligence` Seam

**Files:** `modules/scrapers/company_research.py`, `modules/pipeline.py`

**Problem:** `research_company` hardcodes 4 strategies (Playwright multi-page, crawl4ai, Firecrawl, search) in a fixed priority order. The caller cannot request "just give me funding data from Crunchbase" or "use the cheapest source available." All callers get the same blended text dump.

**Solution:** Define a `CompanyIntelligence` interface with query types: `profile`, `news`, `tech_stack`, `funding`, `culture`. Implement adapters for:

- `WebsiteCrawlerSource` (agent-browser or Crawl4AI for multi-page crawl)
- `SearchAggregateSource` (Exa, DuckDuckGo, Google — for news and recent signals)
- `StructuredCompanyApiSource` (Crawlora, DataFlirt — for Crunchbase + LinkedIn + tech stack)
- `AIBrowserAgentSource` (Browserbase Agents or Browserless Agent — natural language research goals)

The pipeline requests specific intelligence types. The adapter layer picks the cheapest source that can satisfy the request.

**Benefits:**

- **Locality:** "Company research is too slow" is debugged at the seam, not by reading 4 tool integrations.
- **Leverage:** Interview prep, Q&A generation, and cover letter writing can each request different intelligence slices — no more one-size-fits-all text dump.
- **Tests:** Mock the `CompanyIntelligence` seam in pipeline tests; test real adapters independently against live sources.

---

### Candidate 3: Replace Playwright with an MCP-Native or Stealth Browser Stack

**Files:** `modules/scrapers/job_postings.py`, `modules/scrapers/company_research.py`

**Problem:** Playwright is now detectable. JobQuest uses it as the final fallback for JS-heavy pages (Screenloop, SPA company sites). In 2026, this means more failures on anti-bot-protected job boards and slower company research.

**Solution:** Introduce a `StealthBrowser` adapter at the new `JobDataSource` and `CompanyIntelligence` seams. Options:

1. **agent-browser** (Vercel) — already snapshot-based, MCP server available, Rust CLI, integrates with pi harness. Best if we want to stay in the Pi/agent ecosystem.
2. **Veil** — raw CDP, 57/57 stealth score, TypeScript-native. Best for hostile sites (LinkedIn, Cloudflare-protected boards).
3. **Browserless Agent** — MCP-native, persistent sessions, command batching. Fastest for multi-step workflows.

Playwright becomes one adapter behind the seam, not the default.

**Benefits:**

- **Locality:** Browser detection issues are fixed in the `StealthBrowser` adapter, not spread across both scraper files.
- **Leverage:** The same stealth browser serves job posting scraping, company research, and future features (form filling, application tracking).

---

### Candidate 4: Add Schema-Guided Structured Extraction

**Files:** `modules/scrapers/job_postings.py`, `modules/parsers.py`, `modules/pipeline.py`

**Problem:** All scraped job data arrives as flat text (`description` is one long string). The pipeline then asks an LLM to re-parse this text for skills, salary, remote policy, and questions. This is wasteful — modern scrapers can return structured JSON directly.

**Solution:** Define a `JobPost` schema (pydantic or typed dict) with fields:

```
title, company, description, url, source, questions,
salary_range, location, remote_policy, employment_type,
department, required_skills, nice_to_have_skills, posted_date
```

Add a `StructuredExtractor` adapter that uses:

- Firecrawl `/extract` with the schema
- Crawl4AI's LLM extraction with the schema
- Or a local LLM call on the raw HTML

The pipeline receives a fully typed `JobPost`. The downstream LLM steps (tailoring, ATS check, fit evaluation) get pre-structured data and spend fewer tokens re-parsing.

**Benefits:**

- **Locality:** Extraction logic lives in one adapter. When a job board changes layout, the schema stays stable.
- **Leverage:** Fit evaluation, ATS checking, and salary benchmarking all consume typed data — fewer "parse failed" fallbacks.
- **Tests:** Validate extraction output against the schema, not against string containment.

---

### Candidate 5: Replace Exa Discovery with a Dedicated Job Data Feed

**Files:** `scripts/discover_jobs.py`

**Problem:** The discovery script maintains an 80+ query catalog, hand-tuned regex for location whitelisting, company name extraction, and spam filtering. Exa is general semantic search — it returns news articles, personal portfolios, and scraper farms alongside real jobs. The deduplication and filtering logic is ~60% of the file.

**Solution:** Swap the core discovery engine to a dedicated job data source:

1. **Apify JobStream + Hiring-Signal Intel** — normalized, deduplicated, change-tracked feeds from Greenhouse/Lever/Ashby. $2.50 / 1,000 postings. No query catalog needed.
2. **Free Job Postings API** (Launly) — 1.8M+ listings, 30+ ATSs. Filter by role, location, recency via API params.
3. **Exa as augmentation only** — use semantic search for niche boards not covered by structured APIs, not as the primary discovery mechanism.

**Benefits:**

- **Locality:** Location filtering and deduplication are handled by the feed provider, not by 200 lines of regex in `discover_jobs.py`.
- **Leverage:** New job boards are supported when the provider adds them — no query catalog updates.
- **Tests:** Discovery output is validated against the provider's schema, not against a moving target of spam patterns.

---

## 4. Recommended Priority

If I were implementing these today (July 2026), I would order them:

1. **Candidate 1 (`JobDataSource` seam)** — unlocks all others. Without this, every improvement requires editing the same shallow functions.
2. **Candidate 4 (structured extraction)** — immediate token savings and reliability gain.
3. **Candidate 3 (stealth browser)** — fixes the growing anti-bot failure rate.
4. **Candidate 2 (`CompanyIntelligence` seam)** — parallel to 1, but lower pipeline impact.
5. **Candidate 5 (dedicated job feed)** — biggest reduction in maintenance burden, but requires external spend or API migration.

---

## 5. Which Candidate Should We Explore?

I can drill into any of the five candidates above with a grilling loop — walking constraints, dependencies, adapter shapes, and test surfaces. Which one matters most to you right now?
