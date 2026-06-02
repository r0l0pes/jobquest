# P8: Live Discovery Log — Streaming Progress in the Discovery Pop-Up

**Status:** Spec
**Date:** 2026-06-02

## What

When the user starts a job discovery from the Discovery pop-up, the modal
expands and shows a **live streaming log** of what the discovery script is
doing — which query is being searched, how many raw results, dead URL skips,
verification progress. The user can monitor progress, spot hangs, and debug
failures without leaving the browser.

No new windows or tabs. The existing modal grows to accommodate a scrollable
log area between the options and the action buttons.

## Why

Currently, `POST /api/discover` blocks for up to 180 seconds with no feedback
beyond "this might take a while". If the script hangs or crashes, the only
error is a cryptic timeout message with no context on which query failed.
Users need visibility into the discovery process to:

- Know it's not stuck (queries are progressing)
- Spot which query caused a timeout
- See how many dead URLs were skipped
- Verify new jobs were found before closing

## Architecture

```
Browser (job_queue.html)                     serve_tracker.py
┌─────────────────────────────┐             ┌────────────────────────┐
│  Discovery Pop-up           │  POST       │  ThreadingHTTPServer   │
│  ┌─────────────────────────┐│  /api/      │  ┌──────────────────┐  │
│  │ Time: [7d] [24h]        ││  discover   │  │ POST handler:    │  │
│  │ Keep: [Keep] [Remove]   ││──────────→  │  │ 1. Start script   │  │
│  │                         ││             │  │    in background   │  │
│  │ ┌─────────────────────┐ ││  ←──────    │  │ 2. Return job_id  │  │
│  │ │ [12/41] Searching:  │ ││  { job_id }  │  │ 3. Store process  │  │
│  │ │ Senior Growth PM... │ ││             │  │ 4. Capture stderr  │  │
│  │ │ → 8 raw results     │ ││  GET        │  └──────────────────┘  │
│  │ │ → 2 dead URLs       │ ││  /api/      │  ┌──────────────────┐  │
│  │ │ → Verifying 23 jobs │ ││  discover-  │  │ GET handler:     │  │
│  │ └─────────────────────┘ ││  log/<id>   │  │ Return stderr    │  │
│  │                         ││──────────→  │  │ accumulated +    │  │
│  │ [Cancel] [Start]       ││  ←──────    │  │ done/failed flag │  │
│  └─────────────────────────┘│  { lines,   │  └──────────────────┘  │
│                             │    done,    │                         │
│                             │    error }   │                         │
└─────────────────────────────┘             └────────────────────────┘
```

The server switches from `HTTPServer` to `ThreadingHTTPServer` (one-line stdlib
change) so the browser can poll progress while the subprocess runs.

## Changes

### 1. `serve_tracker.py` — Threading, non-blocking discovery, status endpoint

**A. ThreadingHTTPServer** (line ~320 in `main()`)

```python
from socketserver import ThreadingMixIn
# ... instead of HTTPServer(("127.0.0.1", port), TrackerHandler)
# ThreadingHTTPServer is just ThreadingMixIn + HTTPServer
```

Or simply import `ThreadingHTTPServer` from `http.server` (Python 3.7+):

```python
from http.server import ThreadingHTTPServer
server = ThreadingHTTPServer(("127.0.0.1", args.port), TrackerHandler)
```

**B. Global discovery process store** (module level)

```python
import threading
_discovery_store = {}  # job_id -> { "proc": Popen, "stderr": [], "done": False, "error": "" }
_discovery_lock = threading.Lock()
```

**C. `POST /api/discover`** — non-blocking version

- Input: `{ "mode": "7d"|"24h", "clear": true|false }`
- Instead of `subprocess.run(..., timeout=180)`, use `subprocess.Popen` with `stderr=subprocess.PIPE, stdout=subprocess.DEVNULL`
- Generate a unique `job_id` (e.g. `uuid.uuid4().hex[:8]`)
- Store the Popen object and an empty stderr buffer under `_discovery_store[job_id]`
- Start a **daemon reader thread** that reads stderr line by line and appends to the buffer
- Return immediately: `{ "ok": true, "job_id": "..." }`

The reader thread also monitors `proc.poll()`. When the process exits:
- Read any remaining stderr
- Set `store["done"] = True`
- If `returncode != 0`, set `store["error"]` with the stderr tail
- Parse the job count from the queue file

**D. `GET /api/discover-log?job_id=<id>`** — status polling

- Returns the accumulated stderr lines and completion status
- Response: `{ "lines": [...], "done": false, "error": "", "jobs_found": 0 }`
- When done: `{ "lines": [...], "done": true, "error": "", "jobs_found": 12 }`
- On error: `{ "lines": [...], "done": true, "error": "Timeout exceeded", "jobs_found": 0 }`
- After 60 seconds of inactivity (process dead, done=true), the store entry can be cleaned up

**E. `DELETE /api/discover/<job_id>`** — cancel a running discovery

- Kills the Popen process (`proc.kill()`)
- Sets `done = true` with `error = "Cancelled by user"`
- Returns `{ "ok": true }`

**F. Timeout handling**

- The reader thread tracks elapsed time since discovery started
- If `timeout=180` is hit and the process hasn't finished, `proc.kill()`, set `done=true, error="Timed out after 180 seconds"`

### 2. `data/job_queue.html` — Expansive modal with live log

**A. Modal layout changes**

The modal should be taller when expanded with a log. The structure (top to bottom):

```
┌─ Discovery ─────────────────────────────┐
│  Start job discovery?                    │
│                                          │
│  Time range:  ○ Last 7 days  ○ 24 hours │
│  Existing:    ○ Keep  ○ Remove          │
│                                          │
│  ┌──── Discovery Log ──────────────────┐ │
│  │ [12/41] Searching: Senior Growth... │ │
│  │   → 8 raw results                    │ │
│  │   → Verifying 23 URLs...            │ │
│  │   → ✅ Added 5 new jobs             │ │
│  │                                      │ │
│  └──────────────────────────────────────┘ │
│                                          │
│  [Cancel]                    [Start]     │
└──────────────────────────────────────────┘
```

- The log area is a `<pre>` or `<div>` with `font-family: monospace, font-size: 13px`
- Has a max-height of 300px with `overflow-y: auto`
- Auto-scrolls to bottom as new lines arrive
- The log area is initially hidden (display: none) and shown when discovery starts
- The Start button is disabled during discovery, Cancel is enabled
- The Cancel button terminates the discovery run

**B. JavaScript flow**

```javascript
let currentJobId = null;
let pollInterval = null;

async function startDiscovery() {
  const mode = document.querySelector('input[name="discover-mode"]:checked').value;
  const clear = document.querySelector('input[name="discover-clear"]:checked').value === "remove";
  
  // Show log area, disable Start, enable Cancel
  document.getElementById('discovery-log').style.display = 'block';
  document.getElementById('start-btn').disabled = true;
  document.getElementById('cancel-btn').disabled = false;
  appendLogLine('Starting discovery...');
  
  const resp = await fetch("/api/discover", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ mode, clear })
  });
  const result = await resp.json();
  
  if (!result.ok) {
    appendLogLine(`❌ ${result.error}`);
    resetButtons();
    return;
  }
  
  currentJobId = result.job_id;
  appendLogLine(`🔍 Discovery started (id: ${currentJobId})`);
  
  // Start polling
  pollInterval = setInterval(pollLog, 2000);
}

async function pollLog() {
  if (!currentJobId) return;
  
  const resp = await fetch(`/api/discover-log?job_id=${currentJobId}`);
  const data = await resp.json();
  
  // Append any new lines
  if (data.lines && data.lines.length > 0) {
    const logArea = document.getElementById('discovery-log-content');
    data.lines.forEach(line => {
      if (!logArea.dataset.lastCount || parseInt(logArea.dataset.lastCount) < line.index) {
        appendLogLine(line.text);
      }
    });
    logArea.dataset.lastCount = data.lines.length;
  }
  
  if (data.done) {
    clearInterval(pollInterval);
    pollInterval = null;
    if (data.error) {
      appendLogLine(`❌ ${data.error}`);
    } else {
      appendLogLine(`✅ Found ${data.jobs_found} new jobs`);
    }
    // Re-enable Start, disable Cancel, show Close + Reload
    document.getElementById('start-btn').disabled = false;
    document.getElementById('cancel-btn').disabled = true;
    document.getElementById('close-btn').style.display = 'inline';
    document.getElementById('reload-btn').style.display = 'inline';
  }
}

async function cancelDiscovery() {
  if (!currentJobId) return;
  await fetch(`/api/discover/${currentJobId}`, { method: "DELETE" });
  appendLogLine('⏹ Discovery cancelled');
  clearInterval(pollInterval);
  pollInterval = null;
  resetButtons();
}

function appendLogLine(text) {
  const logArea = document.getElementById('discovery-log-content');
  const line = document.createElement('div');
  line.textContent = text;
  logArea.appendChild(line);
  logArea.scrollTop = logArea.scrollHeight;
}

function closeModal() {
  document.getElementById('discovery-modal').style.display = 'none';
}

function reloadPage() {
  location.reload();
}
```

**C. Styling additions**

```css
#discovery-log {
  display: none;
  margin: 12px 0;
  border: 1px solid #333;
  border-radius: 8px;
  background: #1a1a2e;
  max-height: 300px;
  overflow-y: auto;
}

#discovery-log-content {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 13px;
  line-height: 1.5;
  padding: 10px;
  color: #e0e0e0;
}

#discovery-log-content div {
  white-space: pre-wrap;
  word-break: break-all;
}

#close-btn, #reload-btn {
  display: none;
}
```

### 3. No changes to `scripts/discover_jobs.py`

The script already prints detailed progress to stderr. The log endpoint will
capture and stream exactly that output.

## Files Changed

| File | Change |
|------|--------|
| `serve_tracker.py` | ThreadingHTTPServer, non-blocking POST /api/discover, GET /api/discover-log, DELETE /api/discover/<id>, global store with lock |
| `data/job_queue.html` | Expandable modal with live log area, polling JS, Cancel/Close/Reload buttons, scrollable monospace log |

## Test Scenarios

| Category | Scenario |
|----------|----------|
| Happy path | Start discovery with 7d+Keep → POST returns job_id → log polls show progressing queries → done=true → "✅ Found N jobs" shown → Reload works |
| Happy path | Start discovery with 24h+Remove → queue cleared first → discovery runs → jobs appear |
| Happy path | Click Cancel during discovery → DELETE called → log shows "⏹ Discovery cancelled" → buttons reset |
| Happy path | Discovery succeeds, user clicks Close (no reload) → modal closes → manually reloading later shows queue |
| Edge case | Discovery script fails (API error) → done=true with error → log shows error → user can inspect and try again |
| Edge case | Discovery script times out at 180s → done=true with "Timed out" → log shows last lines before timeout |
| Edge case | Start discovery then close modal (dismiss) → polling continues → reopening modal reconnects to same job_id |
| Integration | POST returns immediately (non-blocking) → log polls succeed concurrently → page stays responsive |
| Integration | Discovery is running → Tracker page at / loads in another tab → content served without delay |
