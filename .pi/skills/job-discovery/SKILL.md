---
name: job-discovery
description: Search PM job boards (Germany/Spain), output sortable HTML queue. Trigger: find jobs, discover roles, search market, queue positions.
---

# Job Discovery

## Two modes

| Mode    | Trigger phrases                                               | Recency filter          |
| ------- | ------------------------------------------------------------- | ----------------------- |
| **24h** | "Find jobs from today", "What's new today?", "Last 24 hours"  | Posted in last 24 hours |
| **7d**  | "Find jobs this week", "Search the last week", "What's open?" | Posted in last 7 days   |

If the user doesn't specify, ask which mode they want.

## Workflow

**DO NOT use `web_search`.** Pi's `web_search` tool has a session bug that dies after 1-2 calls. The skill requires 30+ searches — impossible with the broken tool.

Instead, use the dedicated Python script:

```bash
source venv/bin/activate
python scripts/discover_jobs.py --mode 7d   # or --mode 24h
```

The script:
1. Reads the Exa API key from `~/.pi/web-search.json`
2. Runs 38 plain-language semantic searches via direct Exa API calls
3. Extracts structured job data (company, title, URL, location, source)
4. Deduplicates against `data/job_queue.html`
5. Appends new entries to the JOBS array
6. Prints a JSON summary to stdout

After the script runs, read the summary from stderr/stdout and report to the user:
- How many queries ran
- How many new jobs were found
- Breakdown by country and role type

## Output

**All results go to `data/job_queue.html`.** This file already exists with a complete sortable HTML table template. The script appends directly to it — do not manually edit the file unless correcting specific entries.

Each job entry:

```javascript
{ company: "CompanyName", title: "Role Title", url: "https://...", companyUrl: "https://...", location: "City, Country", country: "de", roleType: "growth", date: "YYYY-MM-DD", source: "linkedin" }
```

Fields:

- `url`: Link to the job board posting (always populated)
- `companyUrl`: Direct link to the company's career page (best-effort, may be empty)
- `country`: `"de"`, `"es"`, or `"remote"`
- `roleType`: `"growth"`, `"ai"`, or `"generalist"`
- `date`: Date discovered (YYYY-MM-DD)
- `source`: Platform where found

## Rules

1. **Never use `web_search`.** Always run `python scripts/discover_jobs.py`.
2. **No company names in queries.** The script uses plain-language semantic searches.
3. **No company filtering.** Include all matching roles. The user reviews later.
4. **Volume over precision.** The script handles deduplication and filtering.
5. **If the script fails**, check `~/.pi/web-search.json` has a valid `exaApiKey`.
6. **If results are too noisy**, the script already filters personal profiles and non-job pages. You can add more skip patterns in `scripts/discover_jobs.py` if needed.
