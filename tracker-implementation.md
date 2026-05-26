# Tracker Implementation — Summary

## Changes Made

### 1. `data/applications.json` — deduplicated
- Before: 20 entries (many duplicates from multiple pipeline runs on same URL)
- After: 5 unique entries, deduplicated by normalized URL (stripped hash fragments, trailing slashes)
- Highest-scored entry kept per URL
- All entries now have `status` field

### 2. `data/tracker.html` — enhanced UI
- **Added URL column** — shows truncated URL and links to the job posting (critical for "did I apply to this URL?")
- **Added "Log Application" button** — opens a modal form to manually add jobs applied outside the pipeline
  - Fields: Company, Role, URL, Status (default: Applied)
  - Real-time URL dedup check as you type
  - Prevents duplicate URLs from being added
- **URL search** — search box now filters by company, role, AND URL
- **Same dark theme** — matching `job_queue.html` UX
- **Preserved all existing features** — sortable columns, status dropdowns, notes, save button, analytics overview, funnel visualization

### 3. `serve_tracker.py` — new endpoint
- **`GET /api/check-url?url=...`** — checks if a URL already exists in the tracker
  - Normalizes URLs (strips hash fragments, trailing slashes)
  - Returns `{ "exists": true/false, "matched": { company, role, status, date } }`
- Existing endpoints unchanged: `GET /api/applications`, `POST /api/applications`

### 4. `data/job_queue.html` — URL dedup on "Move to Tracker"
- When moving jobs from the queue to the tracker, URLs are checked against existing tracker entries
- If duplicates found, a confirmation dialog shows which jobs already exist
- User can skip duplicates and still save new entries, or cancel entirely
- Non-duplicates are safely merged into the tracker

## How to Use

```bash
# Start the tracker server
python serve_tracker.py

# Open in browser
open data/tracker.html

# Or via terminal (serves on http://127.0.0.1:7878)
```

## Validated

- ✅ `GET /api/applications` returns 5 deduplicated entries
- ✅ `POST /api/applications` saves correctly
- ✅ `GET /api/check-url?url=...` detects existing URLs (normalized matching)
- ✅ Queue "Move to Tracker" still works and now has URL dedup
- ✅ Manual "Log Application" form works with URL dedup check
