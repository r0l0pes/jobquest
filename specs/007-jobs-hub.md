# P7: Jobs Hub — Unified Launcher with Discovery Pop-Up

**Status:** Spec
**Date:** 2026-06-02

## What

A single entry point (`JobQuest.command`) that launches all three JobQuest
tools in one go — Pipeline, Tracker, and Discovery — each in its own browser
tab. The Discovery tab shows a pop-up on load asking whether to run job
discovery, with configurable time range and queue-clearing options.

## Why

Currently:
- `JobQuest.command` only starts the Pipeline UI (Gradio on port 7860)
- Tracker requires a separate `python serve_tracker.py` command
- Discovery is only accessible via CLI (`python scripts/discover_jobs.py`)
- No unified way to trigger discovery from the browser

This creates friction: the user must manually start servers, remember ports,
and switch to the terminal to run discovery. The Jobs Hub eliminates all of that.

## Architecture

```
JobQuest.command
  ├── Starts serve_tracker.py (port 7880) ← serves Tracker + Discovery pages
  ├── Starts web_ui.py (port 7860)        ← serves Pipeline UI
  └── Opens 3 browser tabs:
       ├── Tab 1: http://127.0.0.1:7860  → Pipeline
       ├── Tab 2: http://127.0.0.1:7880  → Tracker
       └── Tab 3: http://127.0.0.1:7880/queue  → Discovery Queue
```

The tracker server (`serve_tracker.py`) also hosts the Discovery page and the
`/api/discover` endpoint. No new servers needed.

## Changes

### 1. `JobQuest.command`

Replace the current single-launch script with one that:
1. Kills any existing tracker/pipeline processes on the relevant ports
2. Starts `serve_tracker.py --port 7880` in background
3. Starts `web_ui.py` in background
4. Waits briefly for servers to start
5. Opens 3 tabs in the default browser:
   - `http://127.0.0.1:7860` → Pipeline
   - `http://127.0.0.1:7880` → Tracker
   - `http://127.0.0.1:7880/queue` → Discovery

```bash
#!/bin/bash
cd "$(dirname "$0")"

# Kill existing servers
lsof -ti:7860 -ti:7880 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

# Start tracker server (serves Tracker + Discovery + API)
source venv/bin/activate
python serve_tracker.py --port 7880 &
TRACKER_PID=$!

# Start Pipeline UI
python web_ui.py &
PIPELINE_PID=$!

# Wait for servers
sleep 3

# Open 3 tabs
open http://127.0.0.1:7860   # Pipeline
open http://127.0.0.1:7880   # Tracker
open http://127.0.0.1:7880/queue  # Discovery

# Wait
wait $TRACKER_PID $PIPELINE_PID
```

### 2. `serve_tracker.py` — new endpoint + route

**Add `/queue` route** in `do_GET`:
```python
elif self.path == "/queue" or self.path == "/queue/":
    self.path = "/data/job_queue.html"
    super().do_GET()
```

**Add `POST /api/discover`** endpoint:
- Input: `{ "mode": "7d"|"24h", "clear": true|false }`
  - `mode`: time range for discovery (7 days or 24 hours)
  - `clear`: if true, clear `data/job_queue.html` before running (reset to empty template)
- Action:
  1. If clear==true, write empty job_queue.html template
  2. Run `scripts/discover_jobs.py --mode <mode>` via subprocess (timeout: 120s)
  3. Capture stdout/stderr
- Output: `{ "ok": true, "jobs_found": N, "error": "..." }` or `{ "ok": false, "error": "..." }`

### 3. `data/job_queue.html` — discovery pop-up modal

**Add toolbar button:** "Run Discovery" that opens the modal

**Add modal on page load** asking:
- **"Start job discovery?"** (Yes / No)
  - If No → modal closes, shows existing queue
  - If Yes → shows additional options:

- **"Time range"** radio: "Last 7 days" / "Last 24 hours" (default: 7 days)

- **"Existing positions"** radio: "Keep" / "Remove" (default: Keep)

- **"Start Discovery" button** → calls `/api/discover`

- **"Cancel" button** → closes modal

**Modal JS flow:**
```javascript
async function startDiscovery() {
  const mode = document.querySelector('input[name="discover-mode"]:checked').value;  // "7d"|"24h"
  const clear = document.querySelector('input[name="discover-clear"]:checked').value === "remove";
  
  showStatus("⏳ Running discovery...", "info");
  
  const resp = await fetch("/api/discover", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ mode, clear })
  });
  const result = await resp.json();
  
  if (result.ok) {
    showStatus(`✅ Found ${result.jobs_found} new jobs`, "success");
    closeModal();
    location.reload();  // Reload to show updated queue
  } else {
    showStatus(`❌ ${result.error}`, "error");
  }
}
```

**Styling:** Consistent dark theme with the existing tracker/queue CSS.

## Files Changed

| File | Change |
|------|--------|
| `JobQuest.command` | Rewrite to launch all 3 services + open 3 tabs |
| `serve_tracker.py` | Add `/queue` route + `POST /api/discover` endpoint |
| `data/job_queue.html` | Add discovery pop-up modal + "Run Discovery" button |

## Test Scenarios

| Category | Scenario |
|----------|----------|
| Happy path | Open Discovery tab, click Yes → 7d → Keep → Start → discovery runs, queue updates |
| Happy path | Open Discovery tab, click Yes → 24h → Remove → Start → queue cleared, new jobs appear |
| Happy path | Open Discovery tab, click No → modal closes, existing queue shown as-is |
| Edge case | Discovery script fails (API error) → error displayed in modal, queue unchanged |
| Edge case | Server not running → Discovery page shows error on load |
| Integration | JobQuest.command starts all 3 servers and opens 3 tabs |
| Integration | Discovery API called + new jobs appear in queue.html |
