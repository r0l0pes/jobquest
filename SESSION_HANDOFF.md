# Session Handoff — 2026-05-24

## Current State

JobQuest fully operational. 22 tests passing. 181 jobs in `data/job_queue.html` (57 existing + 124 added this session).

## What Changed This Session

### 1. 17 New Job Boards Added
- **`scripts/discover_jobs.py`**: Added 20 new queries (58 total), domain detection in `infer_source()`, and entries in `KNOWN_JOB_BOARDS` for the 17 new boards.
- **`modes/discover.md`**: Updated remote-only board list and query patterns.

New boards: `4dayweek.io`, `jobspresso.co`, `flexjobs.com`, `nodesk.co`, `workingnomads.com`, `trulyremote.co`, `flexa.careers`, `jobgether.com`, `oomple.com`, `careervault.io`, `dailyremote.com`, `remotely.de`, `euremotejobs.com`.

### 2. URL Verification Step Added
- **`scripts/discover_jobs.py`**: Added `verify_job_urls()` — HEAD-request check before appending. Drops 404/410/5xx/dead links. Keeps 200/301/302.
- Marked with a banner comment for easy reversion.
- This session: 36 of 160 deduplicated jobs were dead URLs caught by this check.

### 3. Personal Portfolio Skip Patterns
- **`scripts/discover_jobs.py`**: Added 15 personal portfolio domains + path indicators `/sobre-mi`, `/conoce-a`, `/curriculum`, `/cv/`.

### 4. Resume Filename Change
- `modules/pipeline.py`: `resume_tailored_{Company}.tex` → `Resume_Rodrigo-Lopes.tex`

### 5. Contact Info Update
| Old | New | Files |
|---|---|---|
| `rodrigolopes.eu` | `rodrigolopes.xyz` | `templates/resume.tex`, `modules/pipeline.py` |
| `contact@rodrigolopes.eu` | `contact@rodrigolopes.xyz` | + `prompts/qa_generator.md` |

### 6. Discovery Search Run
- `python scripts/discover_jobs.py --mode 7d` → 124 new jobs added

## Pending Issues

1. **Single-letter company names** — URL extraction produces "Fe", "Ca", "Ra" etc. from domain-part extraction. The `extract_company_from_url` function needs improvement.
2. **New board query noise** — Jobspresso, Flexa queries return review/contact pages. May need better skip patterns.
3. **LLM provider fallback** — Gemini rate limits persist. ATS check step may still fail.
4. **3 test entries in Skills DB v1** — "Test Skill", "Test Skill 2", "Test Skill 3" created during property format debugging. Delete manually.

## Key Files

- `AGENTS.md` — Project overview
- `scripts/discover_jobs.py` — 58 queries, URL verification, skip patterns
- `modules/pipeline.py` — Resume_Rodrigo-Lopes filename, contact info
- `templates/resume.tex` — LaTeX template
- `prompts/qa_generator.md` — Q&A prompt
- `data/job_queue.html` — 181 jobs

## What Changed This Session (2026-05-25)

### 7. WFP → Postscript Replacement (All Resume Variants)
- **Notion Master Resume**: Already had Postscript (done prior session)
- **Notion Generalist PM Resume**: Updated via `notion-update-page` — heading, date line, and all 3 bullets replaced
- **Local template** (`templates/resume.tex`): Already Postscript
- **Pipeline code** (`modules/pipeline.py`): Still references "WFP" internally for AI-PM variant context injection — cosmetic, doesn't affect output

### 8. Skills Databases Updated
- **Database v1** (Job Posting Keywords): `WFP` → `Postscript` in Evidence/Where Used options. Added 9 new skills with rich keyword mappings.
- **Database v2** (ATS Priority): Added new categories (`Platform & Infrastructure`, `Strategy & Leadership`, `Go-to-Market & Growth`) and `Critical` priority. Added 11 new skills.

## What Changed This Session (2026-05-26)

### 9. Postscript Portfolio Rebrand (Portifaria repo)
- WFP → Postscript across case studies, experience, hero, About
- New Postscript case study: AI SMS Personalization for 18,000 Shopify merchants
- Logo: transparent PNG, sized for marquee (`md:h-20`)
- About section tools updated: Kilo Code→Cursor, dropped Codex, VTEX→PostHog, LLM Workflows, Prompt Engineering
- AGENTS.md and SESSION_HANDOFF.md added to portifaria repo

### 10. Job Discovery Run (24h mode)
- `python scripts/discover_jobs.py --mode 24h` → 119 new jobs after dedup + URL verification
- 32 dead URLs filtered out
- Jobs dated 2026-05-26 appended to `data/job_queue.html`

### 11. Tracker UX Verified + Pipeline Dedup Fix
- **`modules/pipeline.py`**: Added URL dedup in `step_create_tracker_entry()` — normalizes URLs, updates existing entry instead of duplicating
- `data/tracker.html` already had: URL column, search, status dropdowns, Log Application modal, analytics dashboard
- `serve_tracker.py` already had: `/api/check-url?url=...` endpoint
- `data/applications.json` already deduplicated to 5 entries

### 12. Skills Audit Report
- **`data/skills_audit_report.md`**: Full cross-reference of master resume vs portfolio About vs job bullet points
- Key gaps identified: 4 core growth skills missing from portfolio (CRO, PLG, Activation & Onboarding, Funnel & Cohort Analysis)
- Master resume tools need updating: add n8n, PostHog, Cursor; replace GitHub Copilot→Cursor, ChatGPT/Claude/Gemini→LLM Workflows
- Notion master resume needs manual update (source of truth)

## Pending Issues

1. **Single-letter company names** — URL extraction produces "Fe", "Ca", "Ra" etc.
2. **New board query noise** — Jobspresso, Flexa queries return review/contact pages.
3. **LLM provider fallback** — Gemini rate limits persist.
4. **Skills audit changes** — Notion master resume + portfolio About need manual updates per audit report.

## Suggested Skills for Next Session

- `job-discovery` — For running another search
- `handoff` — Continue this document
