---
title: "Builder PM Variant + Agentic Skills Update"
type: feature
status: draft
date: 2026-06-11
---

# Builder PM Variant + Agentic Skills Update

## Research Summary

The PM role split into two distinct paths in 2026 (per LinkedIn, Atlassian, FourWeekMBA):

**AI PM** — manages AI products (models, evals, probabilistic systems). Owns: model behavior, eval frameworks, data quality, drift monitoring. The product *is* AI.

**Builder PM** — uses AI to build products. Ships prototypes, writes evals, designs agentic workflows, specs by running. The PM *is* a builder.

Rodrigo is a **Builder PM** who has AI PM experience. The current variants (Growth, Generalist, AI-PM) do not capture this distinction.

---

## Work Breakdown

### 1. Notion — Update Both Resume Pages

Update the Notion master resume pages (Growth PM and Generalist) with:

- Certifications section: add Anthropic 2026 certs (Subagents, Claude Code, AI Fluency)
- Technical Proficiency: rename "AI-Assisted Workflows" → "AI-Assisted & Agentic Workflows"
  - Add: `MCP (Model Context Protocol)`, `Agentic Systems Design`, `Agent-Ready Systems Thinking`
- Postscript bullets: add agentic framing to the SMS optimization work
  - Research: the SMS optimization engine tested hundreds of variants per automation — this is an agentic workflow pattern (automated A/B testing, continuous learning, model-driven optimization). The bullet should surface this as "agentic optimization" not just "AI-powered".

### 2. New Resume Variant: "Builder PM"

Create a new `builder_pm` variant in `web_ui.py` and `config.py`:

- **Tagline**: "Ships product. Uses AI to build." (or similar)
- **Summary**: Foreground prototyping, agentic workflows, MCP, shipping velocity, end-to-end ownership
- **Experience**: Same roles, but bullets re-ordered/rewritten to emphasize:
  - Postscript: AI-powered message optimization → agentic A/B testing at scale
  - FORVIA: B2B platform + self-serve activation → agent-ready systems thinking
  - Accenture: 4-country rollout → rapid prototyping and shipping under ambiguity
  - C&A: Checkout optimization → data-driven builder mindset
- **Skills**: Lead with AI-assisted & Agentic Workflows, then Tools, then Platforms
- **Notion page**: Create a new Notion page for the Builder PM variant (or reuse the Growth PM page with a different framing)

### 3. Discovery Expansion

- Add `builder` as a new role type in `discover_jobs.py` (or tag as `ai` for now)
- Add queries for:
  - `Product Builder Germany`
  - `AI-native Product Manager remote`
  - `Agentic AI Product Manager Europe`
  - `Product Manager AI Interfaces Berlin`
- Expand title filtering to catch: `builder`, `agentic`, `ai-native`, `ai interfaces`, `ai growth`
- Add `automation` as a company extraction keyword

### 4. Prompt Strategy — Minimal, Contextual

Do NOT add lines to existing prompts. Instead:

- **Option A**: Create a new `prompts/builder_context.md` (200-300 words) that gets injected into the tailoring prompt when `ROLE_VARIANT == "builder_pm"`. This tells the LLM: "The candidate is a Builder PM who ships prototypes and uses AI as a primary tool. Frame the summary around shipping velocity, agentic workflows, and end-to-end ownership."
- **Option B**: Add a `variant_context` dict in `pipeline.py` that maps `ROLE_VARIANT` to a short paragraph. Injected at the top of the resume tailor prompt. No new prompt files.

Recommended: **Option B** — keeps the prompt count constant, adds ~50 lines to `pipeline.py`.

### 5. Postscript Case Study — Agent-Ready Systems

Research the Postscript work to find the agentic framing:

- The SMS optimization engine used predictive analytics + generative AI to test hundreds of variants per automation → this is an **agentic optimization loop**: model generates variants, tests them, learns, improves
- The analytics instrumentation across 18,000+ merchant accounts → **structured data for automated systems** (agents need clean data to act on)
- The SMS compliance opt-in redesign → **designing for human operators + automated systems** (one-tap mobile opt-in simplifies the interface for both humans and automation)

Create a specific resume bullet:

```
Designed the SMS optimization engine as an agentic system: generative AI produces message variants, predictive analytics scores them, and the system ships the winner without manual review. This agentic loop drove a 28% increase in earnings-per-message while maintaining brand compliance across 18,000+ merchant accounts.
```

This bullet directly maps to Aignostics' "agentic workflows" and "AI interfaces" requirements.

### 6. Non-PM Title Expansion

The FORMEL SKIN role ("AI Growth & Automation Manager") is not a PM title. Should we add a new `hybrid` role type or just include these in discovery?

Options:
- **Add to Growth PM**: `AI Growth & Automation Manager` → `roleType: "growth"` (closest match)
- **New role type**: `hybrid` for roles that blend PM + ops + growth
- **Tag as Generalist**: Catch-all for non-standard titles

Recommended: **Add to Growth PM**. The title filtering already catches `ai growth` and `automation`. The role type can stay `growth`.

### 7. Testing

- `pytest tests/ -v` must pass after all changes
- Add test for new `builder_pm` variant in `test_pipeline.py` or `test_tracker.py`
- Test discovery script with new queries

---

## Files to Change

| File | Change |
|------|--------|
| `config.py` | Add `builder_pm` to ROLE_VARIANT |
| `web_ui.py` | Add "Builder PM" variant to RESUME_VARIANTS |
| `modules/pipeline.py` | Add `builder_pm` tagline, variant context injection, AI signal detection |
| `scripts/discover_jobs.py` | Add builder/agentic queries, expand title filtering |
| `modes/discover.md` | Add Builder PM role type to target roles |
| `prompts/` | Add `builder_context.md` or use Option B |
| `data/job_queue.html` | Add `builder` to JS filter options |
| Notion pages | Update both master resume pages |

---

## Scope Exclusions

- No new external dependencies (pi, mcp, etc.)
- No changes to the core pipeline logic (15 steps remain unchanged)
- No changes to ATS check, QA generator, or cover letter prompts (unless needed)
- No changes to tracker server API

---

## Verification

- `pytest tests/ -v` passes
- Dry run: `python apply.py "URL" --dry-run` with `ROLE_VARIANT=builder_pm`
- Discovery: `python scripts/discover_jobs.py --mode 7d --queries 3` runs without errors
