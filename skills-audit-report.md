All 22 tests pass. Here's the final summary:

---

## Done

### 1. Enhanced Tracker (`data/tracker.html`)
- **URL search** — search box now scans company, role, AND URL
- **URL column** — dedicated column showing truncated URL with link
- **+ Log Application** — modal form to manually add entries with URL dedup check
- **Status dropdowns** — Applied / Screening / Interview / Offer / Rejected / Skipped
- **Analytics dashboard** — total, response rate, score breakdown, funnel (unchanged, kept)

### 2. URL Dedup Endpoint (`serve_tracker.py`)
- `GET /api/check-url?url=...` returns `{ exists: true, matched: { company, role, status, date } }`

### 3. Cleaned `applications.json`
- 18 duplicates → 5 unique entries

### 4. Skills Audit Report (`data/skills_audit_report.md`)
Complete cross-reference between master resume, portfolio About, prompts, and bullet points. Key findings:
- **Add to portfolio:** CRO, PLG, Activation & Onboarding, Funnel & Cohort Analysis (4 core growth skills)
- **Update master resume tools:** Add n8n, PostHog, Cursor (replace GitHub Copilot)
- **Prompt is correct** — it just needs the source data (master resume) updated first

---

### ⚠ One issue: Pipeline re-adds duplicates
The pipeline appends to `applications.json` without checking for existing URLs. Every time `apply.py` runs for the same job, it duplicates. I can fix this in `modules/pipeline.py` — want me to?