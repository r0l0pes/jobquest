# Job Discovery Run Log

Records every `/skill:job-discovery` attempt, what was tried, what failed, and what was learned.
Read this before starting a new run to avoid repeating mistakes.

---

## Attempt 1 — 2026-05-22 (before ~18:30 UTC)

**Status:** ❌ FAILED — infinite loop / agent stuck

### What happened
User asked for jobs from last 7 days including last 24h. Agent launched 8 parallel `web_search` queries. All 8 failed immediately with:

```
No search provider available. Either:
  1. Set perplexityApiKey in ~/.pi/web-search.json
  2. Set EXA_API_KEY (or exaApiKey) in ~/.pi/web-search.json
  3. Set GEMINI_API_KEY in ~/.pi/web-search.json
```

The job-discovery skill mandates "10+ search rounds minimum." With every search failing, the agent retried repeatedly, getting stuck in an infinite loop. User typed `/btw` to interject, which killed the session.

### Root cause
`~/.pi/web-search.json` did not exist. The `web_search` tool reads API keys from this config file (or env vars), but `EXA_API_KEY` was not set in either location. The user's `GEMINI_API_KEY` was in the environment but the tool requires it in `~/.pi/web-search.json`, not env.

### Evidence
- Session logs: `~/.pi/agent/sessions/--Users-carvalho-Documents-VibeCoding-JobSearch--/2026-05-22T16-39-47-862Z_019e508e-ab96-76f1-aff6-201d230245ad.jsonl`
- Subagent artifacts: `subagent-artifacts/` (from earlier pipeline debugging, not job-discovery)

---

## Attempt 2 — 2026-05-22 (after ~18:30 UTC)

**Status:** ❌ FAILED — Exa-only config, query patterns use Google `site:` syntax

### What changed
- Created `~/.pi/web-search.json` with Exa API key: `2724f844-6bf4-4b7a-909e-8a1ccaf21269`
- Verified: `web_search` test query returned results successfully

### What went wrong
All 8 parallel searches returned **"No result provided"** because the REFERENCE.md query patterns use Google-specific `site:linkedin.com/jobs` syntax. Exa does semantic search and doesn't understand `site:` operators — it treated them as literal text.

### What was learned
- Exa doesn't support Google-style `site:` search operators
- The job-discovery skill REFERENCE.md needs either Gemini web search (which uses Google) or rewritten queries

### Config after this attempt
```
~/.pi/web-search.json: { exaApiKey: "2724f844-..." }
```

---

## Attempt 3 — 2026-05-22 (immediately after Attempt 2)

**Status:** ✅ READY

### What changed
- Added `geminiApiKey` to `~/.pi/web-search.json` alongside Exa key
- Gemini web search uses Google Search under the hood, which supports `site:` operators
- The REFERENCE.md query patterns will work with Gemini

### Current config
```json
{
  "exaApiKey": "2724f844-6bf4-4b7a-909e-8a1ccaf21269",
  "geminiApiKey": "<redacted>"
}
```

### Run details
- **Mode:** 7d (last 7 days, includes last 24h)
- **Current date:** May 22, 2026 (so dates May 15-22)
- **Model:** deepseek/deepseek-v4-flash
- **Existing queue:** `data/job_queue.html` has ~48 jobs from May 4-7 (stale)
- **Query patterns:** Use Gemini web search provider for Google `site:` queries

---

## Run Log Template

For each future run, copy this section and fill it in:

```markdown
## Attempt N — YYYY-MM-DD HH:MM

**Status:** ✅ SUCCESS / ❌ FAILED / ⏳ INCOMPLETE

### Searches attempted
- Query 1: [result count / error]
- Query 2: [result count / error]
- ...

### Jobs found
- Total: N
- By country: DE=X, ES=Y, remote=Z
- By role: Growth=X, AI=Y, Generalist=Z

### Errors encountered
- [error description]

### What was learned
- [insight for next run]
```

## Attempt 4 — 2026-05-22 (~19:00 UTC)

**Status:** ❌ FAILED — `web_search` tool unstable + `site:` queries fail

### What happened
Agent tried to run `/skill:job-discovery` in an aside conversation.

1. First test query worked: `"Senior Growth Product Manager" Germany site:linkedin.com/jobs` returned 3 real LinkedIn results ✅
2. Then ran 6 parallel `site:` queries (Growth DE, Growth DE StepStone, AI DE, Generalist DE, Growth ES, Generalist ES) — **all returned "No result provided"**
3. Tested without `site:` — plain queries also returned "Tool web_search not found"
4. `fetch_content` and `code_search` also returned "Tool not found"

### Root causes (updated understanding)
- The `web_search` provider backend (Gemini/Exa) silently fails on `site:` syntax
- After the first successful call, all web access tools disappear from the runtime
- This is a pi infrastructure issue, not a user config issue

### What was learned
- Even with both API keys in `~/.pi/web-search.json`, the tool is unreliable
- REFERENCE.md queries MUST be rewritten to not rely on `site:` syntax
- OR use a Python script with direct Exa API calls (bypasses `web_search` tool)

## Attempt 5 — 2026-05-22 (this session, Kimi K2.6 diagnosis)

**Status:** ❌ CONFIRMED BROKEN — `web_search` tool wrapper dies after 1-2 calls

### Reproduction
Agent was asked to diagnose the issue. Ran 5 sequential `web_search` calls:

| # | Query | Result |
|---|-------|--------|
| 1 | `"Senior Growth Product Manager jobs Germany 2026"` (plain) | ✅ 4 results |
| 2 | `"Senior Growth Product Manager" Germany site:linkedin.com/jobs` | ✅ 3 results |
| 3 | `"Senior Product Manager" Germany startup site:linkedin.com/jobs` | ✅ 4 results |
| 4 | `"Senior AI Product Manager" Germany site:linkedin.com/jobs` | ❌ "No result provided" |
| 5 | `"Senior Growth Product Manager" Spain site:linkedin.com/jobs` | ❌ "No result provided" |

### Control test
Direct Exa API call via Python `requests` using same API key (`2724f844-...`) — **all queries succeeded**. The Exa API is fine. Pi's `web_search` tool wrapper is the failure point.

### Conclusion
The `web_search` tool has a session bug: it works for 1-2 calls then silently returns "No result provided". The skill requires 10+ calls. It is mathematically impossible for this skill to complete using pi's `web_search`.

### Fix required
Build `scripts/discover_jobs.py` using direct Exa API calls (bypasses broken tool). Update skill to run Python script instead of `web_search`.

### Recommended fix
1. Build `scripts/discover_jobs.py` (direct Exa API, plain-language queries)
2. Update `modes/discover.md` to use Python script
3. Update `REFERENCE.md` to remove all `site:` syntax

---

## Attempt 5 — 2026-05-22 (~20:00 UTC)

**Status:** ❌ FAILED — `web_search` tool dies after 1-2 calls (CONFIRMED)

### What happened
User switched to Kimi K2.6 to diagnose the issue. Agent ran diagnostic `web_search` calls:
1. `web_search` plain query: `"Senior Growth Product Manager jobs Germany 2026"` → 4 results ✅
2. `web_search` `site:` query: `"Senior Growth Product Manager" Germany site:linkedin.com/jobs` → 3 real LinkedIn results ✅
3. `web_search` `site:` query: `"Senior Product Manager" Germany startup site:linkedin.com/jobs` → 4 results ✅
4. `web_search` `site:` query: `"Senior AI Product Manager" Germany site:linkedin.com/jobs` → **"No result provided"** ❌
5. `web_search` `site:` query: `"Senior Growth Product Manager" Spain site:linkedin.com/jobs` → **"No result provided"** ❌

Same exact pattern as Attempt 4: works for 1-2 calls, then dies.

### Additional diagnosis
Agent verified with direct Python `requests` call to Exa API:
```python
requests.post('https://api.exa.ai/search', headers=headers, json=payload)
```
Result: **Exa API works perfectly. Multiple sequential calls all succeed.**

This proves the bug is in **pi's `web_search` tool wrapper**, not the underlying Exa/Gemini APIs.

### Root cause (final)
The pi `web_search` tool has a session-level bug where it becomes unresponsive after 1-2 calls. This is reproducible across models (DeepSeek V4, Kimi K2.6) and providers (Exa, Gemini). The underlying APIs are fine.

### What was learned
- **Direct API calls are the only reliable path.** Any solution using pi's `web_search` will fail on a 10+ round search session.
- The job-discovery skill MUST be rewritten to use Python `requests` to Exa API directly, not the `web_search` tool.
- No amount of query rewriting (Option A) will fix this — the tool wrapper itself is the failure point.

### Recommended fix (updated)
Build `scripts/discover_jobs.py` using direct Exa API calls. The skill becomes:
1. Agent writes/updates `scripts/discover_jobs.py` with search parameters
2. Agent runs: `python scripts/discover_jobs.py`
3. Script calls Exa API directly → outputs structured job data
4. Agent parses output → appends to `data/job_queue.html`

This is the only viable path. The `/skill:job-discovery` workflow as currently designed (using pi `web_search`) is fundamentally broken.

