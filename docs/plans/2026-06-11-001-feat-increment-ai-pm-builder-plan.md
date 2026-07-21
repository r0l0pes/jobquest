---
title: "Increment AI-PM Variant with Builder Profile + Discovery Expansion"
type: feat
status: active
date: 2026-06-11
origin: docs/plans/2026-06-11-builder-pm-variant.md
---

# Increment AI-PM Variant with Builder Profile + Discovery Expansion

## Summary

The 2026 PM market has split into "AI PM" (manages AI products) and "Builder PM" (uses AI to build products). Rodrigo is both. This plan increments the existing AI-PM resume variant to foreground the builder differentiator (prototyping, shipping, MCP, agentic workflows) while preserving the AI PM foundation (Postscript AI work). It also expands job discovery to catch Builder PM / AI-PM hybrid roles that are emerging in the market.

---

## Problem Frame

The current AI-PM variant uses the Growth PM Notion page as its base and injects AI context via `research/ai_pm_context.md`. The framing is: "AI products, from 0 to 1." This is accurate for pure AI PM roles but undersells the builder capability — shipping prototypes, using MCP, building multi-provider LLM pipelines. Companies hiring for "AI interfaces," "agentic workflows," or "product builder" roles expect a hybrid profile. The AI-PM variant needs to speak this language.

Additionally, the discovery script (`discover_jobs.py`) does not catch the emerging "Builder PM" / "AI-PM hybrid" roles. Titles like "Product Manager (Builder)," "AI Growth & Automation Manager," "Product Manager — AI Interfaces" are invisible in the current query catalog.

---

## Requirements

- R1. The AI-PM variant's tagline and summary must foreground the builder differentiator
- R2. The injected AI context (`research/ai_pm_context.md`) must be updated with builder evidence from GitHub repos
- R3. The pipeline must inject the updated AI context when `ROLE_VARIANT == "ai_pm"`
- R4. The web UI must continue to show "AI-PM" as the variant label (no new variant)
- R5. Discovery queries must catch builder / AI-PM hybrid roles
- R6. Title filtering must catch `builder`, `agentic`, `ai-native`, `ai interfaces`, `ai growth`
- R7. All 193 tests must pass after changes
- R8. The plan must not create new prompt files (Option B: inline context injection)

---

## Scope Boundaries

- No new resume variant is created — the AI-PM variant is incremented
- No new Notion page is created — the existing Growth PM page is reused
- No changes to the core pipeline logic (15 steps remain unchanged)
- No changes to ATS check, QA generator, or cover letter prompts
- No changes to tracker server API
- No new external dependencies
- The Notion page content is NOT updated by this plan — that's a separate manual step

### Deferred to Follow-Up Work

- Update Notion master resume pages with builder skills (manual step, separate session)
- Create a dedicated Builder PM Notion page (if needed in the future)
- Update the Generalist resume variant with builder skills (if needed)

---

## Context & Research

### Relevant Code and Patterns

- `config.py` — defines `ROLE_VARIANT` options
- `web_ui.py` — defines `RESUME_VARIANTS` and `role_variant_map`
- `modules/pipeline.py` — defines `TAGLINES`, `step_tailor_resume()`, and `_load_ai_pm_context()`
- `research/ai_pm_context.md` — injected AI context for AI-PM variant
- `scripts/discover_jobs.py` — query catalog and title filtering
- `modes/discover.md` — target roles for discovery

### Institutional Learnings

- The `ai_pm_context.md` file was previously 200 words. This plan expands it to ~500 words.
- The pipeline already has `ai_pm_variant` and `qa_ai_pm_variant` boolean flags. The builder context is additive.
- The `research/` directory is the correct place for injected context docs.

### External References

- Builder PM research: `docs/plans/builder_pm_research.md`
- Postscript research: `portifaria/copy-content/postscript_research.md`
- 2026 loop engineering discourse: June 7-11, 2026 (Steinberger, Cherny, Osmani)

---

## Key Technical Decisions

- **Keep the "AI-PM" label**: The user explicitly chose to increment the AI-PM variant rather than create a new one. The builder capability is additive, not a separate identity.
- **Option B for prompt injection**: Add a `variant_context` dict in `pipeline.py` rather than creating a new prompt file. This keeps the prompt count constant and avoids increasing complexity.
- **Use "AI-powered message optimization loop"**: The honest framing for Postscript Infinity Testing — it generates, tests, learns, and improves over time, but has human approval gates.
- **Discovery queries as additions**: New builder/agentic queries are added to the existing query catalog, not replacing existing queries.

---

## Implementation Units

### U1. Update `research/ai_pm_context.md` with Builder Evidence

**Goal:** Expand the AI-PM context file to include the builder differentiator from GitHub repos.

**Requirements:** R1, R2

**Dependencies:** None

**Files:**
- Modify: `research/ai_pm_context.md`
- Test: `tests/test_pipeline.py` (verify context injection loads correctly)

**Approach:**
- Expand the file from ~200 words to ~500 words
- Add a "Builder Evidence" section with AgenticHealth, JobQuest, Context7, and portfolio
- Update the "Honest Framing Rules" section with 2026 loop engineering context
- Use the honest framing: "AI-powered message optimization loop" (not "agentic system")
- Include the June 2026 loop engineering discourse as context

**Execution note:** Test-first — write a test that verifies the context file loads and has the expected content.

**Test scenarios:**
- Happy path: `_load_ai_pm_context()` returns the updated file with builder section
- Edge case: File exists and is readable
- Error path: File does not exist (fallback to empty string)

**Verification:**
- `_load_ai_pm_context()` returns the updated text
- The file includes "Builder Evidence" section
- The file includes "AI-powered message optimization loop" framing

---

### U2. Update `modules/pipeline.py` — Tagline and Q&A Framing

**Goal:** Update the AI-PM tagline to foreground builder capability, and update Q&A framing.

**Requirements:** R1, R3

**Dependencies:** U1

**Files:**
- Modify: `modules/pipeline.py`
- Test: `tests/test_pipeline.py` (verify tagline and Q&A framing)

**Approach:**
- Change tagline from "AI products, from 0 to 1." to "AI products shipped. Prototypes to production."
- Update `role_framing` dict in Q&A section to include builder context
- The `ai_context_section` in `step_tailor_resume()` already injects the AI context — this unit verifies the context is properly loaded

**Execution note:** Test-first — write tests for the new tagline and Q&A framing.

**Test scenarios:**
- Happy path: `TAGLINES["ai_pm"]` returns the new tagline
- Happy path: `role_framing["ai_pm"]` includes builder context
- Edge case: Default tagline (when `ROLE_VARIANT` is not found) still returns `"growth_pm"`

**Verification:**
- `TAGLINES["ai_pm"]` is "AI products shipped. Prototypes to production."
- The pipeline loads the updated AI context when `ROLE_VARIANT == "ai_pm"`

---

### U3. Update `modules/pipeline.py` — Inline Builder Context Injection

**Goal:** Add a `variant_context` dict that maps `ROLE_VARIANT` to a short builder paragraph.

**Requirements:** R8

**Dependencies:** U1

**Files:**
- Modify: `modules/pipeline.py`
- Test: `tests/test_pipeline.py`

**Approach:**
- Add a `variant_context` dict near `TAGLINES` in `pipeline.py`
- The dict maps `"ai_pm"` to a short paragraph about builder capability
- Inject this context at the top of the resume tailor prompt when `ROLE_VARIANT == "ai_pm"`
- This is a lightweight alternative to creating a new prompt file

**Execution note:** Test-first — verify the context is injected correctly.

**Test scenarios:**
- Happy path: When `ROLE_VARIANT == "ai_pm"`, the builder context is injected
- Edge case: When `ROLE_VARIANT == "growth_pm"`, no builder context is injected
- Edge case: When `ROLE_VARIANT` is not in the dict, no context is injected

**Verification:**
- The `variant_context` dict exists and has `"ai_pm"` key
- The builder context is injected into the resume tailor prompt

---

### U4. Update `scripts/discover_jobs.py` — Builder/Agentic Queries

**Goal:** Add queries to catch builder / AI-PM hybrid roles.

**Requirements:** R5, R6

**Dependencies:** None

**Files:**
- Modify: `scripts/discover_jobs.py`
- Test: `tests/test_tracker.py` (verify title filtering catches new keywords)

**Approach:**
- Add ~12 new queries to `QUERY_CATALOG` for builder/agentic roles
- Expand `pm_signals` list to include `builder`, `agentic`, `ai-native`, `ai interfaces`, `ai growth`
- Expand `title_words` set to include `builder`, `agentic`, `automation`, `interfaces`
- Add `automation` as a company extraction keyword

**Execution note:** Test-first — verify the new queries are included in the catalog.

**Test scenarios:**
- Happy path: `result_to_job()` accepts titles with "builder" keyword
- Happy path: `result_to_job()` accepts titles with "agentic" keyword
- Happy path: `result_to_job()` accepts titles with "ai interfaces" keyword
- Edge case: `result_to_job()` still rejects non-PM titles like "software engineer"
- Error path: Excluded titles are still rejected

**Verification:**
- The query catalog includes builder/agentic queries
- Title filtering catches new keywords
- Company extraction works for new keywords

---

### U5. Update `modes/discover.md` — Builder PM Role Type

**Goal:** Add "Builder PM" to the target roles list in the discovery mode doc.

**Requirements:** R5

**Dependencies:** None

**Files:**
- Modify: `modes/discover.md`
- Test: None (documentation-only change)

**Approach:**
- Add "Builder PM" as a target role in the discover mode
- Include example queries for builder roles
- Note that builder roles are currently tagged as `roleType: "ai"` in the queue

**Verification:**
- The discover mode doc includes builder PM queries

---

### U6. Run Full Test Suite

**Goal:** Verify all 193 tests pass after all changes.

**Requirements:** R7

**Dependencies:** U1, U2, U3, U4

**Files:**
- Test: `tests/test_pipeline.py` (verify pipeline changes)
- Test: `tests/test_tracker.py` (verify discovery changes)
- Test: `tests/` (full suite)

**Approach:**
- Run `pytest tests/ -v`
- Verify no regressions
- Add new tests for builder context injection if missing

**Test scenarios:**
- Happy path: All 193 tests pass
- Error path: Any failures are fixed before marking done

**Verification:**
- `pytest tests/ -v` exits with 0
- All 193 tests pass

---

## System-Wide Impact

- **Interaction graph:** The pipeline's `step_tailor_resume()` and `step_generate_qa()` already have AI-PM variant logic. The builder context is additive and does not change existing paths.
- **Error propagation:** `_load_ai_pm_context()` returns empty string if file is missing. This is already handled.
- **State lifecycle risks:** No persistent state changes.
- **API surface parity:** The web UI's `RESUME_VARIANTS` and `role_variant_map` already have the "AI-PM" label. No changes needed.
- **Integration coverage:** The `ai_pm_context.md` is loaded by `_load_ai_pm_context()` which is called by `step_tailor_resume()` and `step_generate_qa()`. The integration is verified by pipeline tests.
- **Unchanged invariants:** The core pipeline 15-step logic, ATS check, Q&A generator, and tracker server API are unchanged.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Postscript framing is overstated | Use "AI-powered message optimization loop" (honest) not "agentic system" |
| Builder context is too verbose | Keep to ~500 words; the injected context is already a summary |
| Discovery queries return too many non-PM results | Tighten title filtering; test with `--max-per-query 2` |
| Tests fail due to pipeline changes | Run full test suite after each unit; fix before proceeding |
| Notion page is NOT updated by this plan | Document as manual step; the cache files are updated separately |

---

## Documentation / Operational Notes

- Update `postscript_research.md` with honest framing
- Update `builder_pm_research.md` with loop engineering context
- The `ai_pm_context.md` file now includes builder evidence

---

## Sources & References

- **Origin document:** `docs/plans/2026-06-11-builder-pm-variant.md`
- Research: `portifaria/copy-content/builder_pm_research.md`
- Research: `portifaria/copy-content/postscript_research.md`
- Related code: `modules/pipeline.py`, `scripts/discover_jobs.py`, `web_ui.py`, `config.py`
- External docs: 2026 loop engineering discourse (Steinberger, Cherny, Osmani)
