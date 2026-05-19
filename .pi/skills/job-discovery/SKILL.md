---
name: job-discovery
description: Search for PM jobs across remote and local boards in Germany and Spain, outputting results to a sortable HTML queue. Use when the user asks to find jobs, discover roles, search the market, check what's new, or queue positions.
---

# Job Discovery

## Two modes

| Mode    | Trigger phrases                                               | Recency filter          |
| ------- | ------------------------------------------------------------- | ----------------------- |
| **24h** | "Find jobs from today", "What's new today?", "Last 24 hours"  | Posted in last 24 hours |
| **7d**  | "Find jobs this week", "Search the last week", "What's open?" | Posted in last 7 days   |

If the user doesn't specify, ask which mode they want.

## Workflow

1. **Confirm mode** — 24h or 7d. Ask if ambiguous.
2. **Search** — Use query patterns from [REFERENCE.md](REFERENCE.md). 10+ rounds minimum. Target 40-80 jobs.
3. **Deduplicate** — Before adding each job, check `data/job_queue.html` JOBS array:
   - Same URL → skip
   - Same company + same title → skip
   - More than 2 jobs from the same company already in queue → skip
4. **Find company URLs** — For each job, best-effort search for the company's direct career page. Store as `companyUrl`. If the lookup fails, leave the field empty or copy the board link. Never block discovery on this step.
5. **Append** — Add new entries to the `JOBS` array in `data/job_queue.html`.

## Search strategy

Rotate through role types (Growth PM, AI PM, Generalist PM) × locations (Germany, Spain) × platforms. Mix English, German, and Spanish queries. See REFERENCE.md for the full query catalog.

## Output

**All results go to `data/job_queue.html`.** This file already exists with a complete sortable HTML table template (search, filters, dark theme). Do not create a new file — append to the existing `JOBS` array inside the `<script>` tag.

Each job entry:

```javascript
{ company: "CompanyName", title: "Role Title", url: "https://...", companyUrl: "https://...", location: "City, Country", country: "de", roleType: "growth", date: "YYYY-MM-DD", source: "linkedin" }
```

Fields:

- `url`: Link to the job board posting (always populated)
- `companyUrl`: Direct link to the company's career page or job listing (best-effort, may be empty)
- `country`: `"de"`, `"es"`, or `"remote"` for location-independent roles
- `roleType`: `"growth"`, `"ai"`, or `"generalist"`
- `date`: Date posted or discovered (YYYY-MM-DD)
- `source`: Platform where found (linkedin, stepstone, infojobs, wellfound, weworkremotely, remoteok, himalayas, remotive, etc.)

Group entries by country then role type with comments. The existing file uses `// 🇩🇪 Germany — Growth PM` style section headers — follow that convention.

## Rules

1. **No company names in queries.** Role title + location only.
2. **No company filtering.** Include all matching roles. The user reviews later.
3. **10+ search rounds minimum.** First 3 rounds surface big companies. Rounds 5-10 surface startups.
4. **Rotate phrasings.** "Growth PM" vs "Product Manager Growth" vs "Senior PM Growth" return different results.
5. **Search in German and Spanish** alongside English. Local-language queries find companies English queries miss.
6. **Volume over precision.** If the role title matches, include it. No quality pre-judging.
