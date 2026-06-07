#!/usr/bin/env python3
"""JobQuest Tracker Server.

Serves tracker.html and handles applications.json read/write.
Zero dependencies beyond Python stdlib. No Flask, no FastAPI.

Usage:
    python serve_tracker.py          → http://localhost:7878
    python serve_tracker.py --port 9000
"""

import argparse
import json
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
APP_FILE = DATA_DIR / "applications.json"

# ── Discovery background state ─────────────────────────────────────────────
_discovery_lock = threading.Lock()
_discovery_status = {"running": False, "started_at": 0, "jobs_found": 0, "error": None}


class TrackerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Prevent browser caching of HTML pages (tracker, discovery queue)
        # so refreshed jobs always show instead of stale cached versions
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/applications":
            self._serve_json()
        elif self.path.startswith("/api/check-url"):
            self._check_url()
        elif self.path == "/api/discover/status":
            self._discover_status()
        elif self.path == "/" or self.path == "":
            self.path = "/data/tracker.html"
            super().do_GET()
        elif self.path == "/queue" or self.path == "/queue/":
            self.path = "/data/job_queue.html"
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/applications":
            self._save_json()
        elif self.path == "/api/recompile":
            self._recompile_pdf()
        elif self.path == "/api/discover":
            self._discover_jobs()
        else:
            self.send_response(404)
            self.end_headers()

    def _check_url(self):
        """Check if a URL already exists in applications.json.
        Normalizes URLs by stripping hash fragments and trailing slashes.
        """
        from urllib.parse import urlparse, urlunparse
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        params = {}
        for pair in query.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v
        target = params.get("url", "")
        if not target:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "missing url parameter"}')
            return

        def normalize(u):
            p = urlparse(u)
            return urlunparse((p.scheme, p.netloc, p.path.rstrip("/") or "/", "", "", ""))

        target_norm = normalize(target)
        result = {"exists": False, "matched": None}
        if APP_FILE.exists():
            apps = json.loads(APP_FILE.read_text())
            for a in apps:
                if normalize(a.get("url", "")) == target_norm:
                    result = {
                        "exists": True,
                        "matched": {
                            "company": a.get("company"),
                            "role": a.get("role"),
                            "status": a.get("status"),
                            "date": a.get("date"),
                        },
                    }
                    break
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def _serve_json(self):
        if APP_FILE.exists():
            data = json.loads(APP_FILE.read_text())
        else:
            data = []
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _save_json(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            APP_FILE.write_text(json.dumps(data, indent=2))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _recompile_pdf(self):
        """
        POST /api/recompile
        Body: { "app_idx": 0, "field": "cover_letter"|"resume", "content": "..." }
        
        Writes the updated .tex content to disk and runs render_pdf.py.
        """
        import subprocess
        from io import StringIO
        
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            apps = json.loads(APP_FILE.read_text())
            idx = int(data["app_idx"])
            field = data["field"]
            content = data["content"]

            if idx < 0 or idx >= len(apps):
                raise ValueError(f"Index {idx} out of range")

            app = apps[idx]
            path_key = field  # "cover_letter" or "resume"
            tex_path = app.get(path_key, "")

            if not tex_path or not Path(tex_path).exists():
                # No existing file path, try to create one from run_dir
                run_dir = app.get("run_dir", "")
                if run_dir:
                    rd = Path(run_dir)
                    if field == "cover_letter":
                        tex_path = str(rd / "Cover-Letter_RodrigoLopes.tex")
                    else:
                        tex_path = str(rd / "Resume_Rodrigo-Lopes.tex")
                    Path(tex_path).parent.mkdir(parents=True, exist_ok=True)

            if not tex_path:
                raise FileNotFoundError(f"No {field} path configured for this entry")

            # Write content to .tex file
            Path(tex_path).write_text(content)

            # Update the app entry in memory
            content_key = f"{field}_content"
            app[path_key] = tex_path
            app[content_key] = content

            # Run render_pdf.py to regenerate PDF
            script = PROJECT_ROOT / "render_pdf.py"
            if script.exists():
                result = subprocess.run(
                    [sys.executable, str(script), tex_path],
                    capture_output=True, text=True, timeout=30
                )
                output = result.stdout.strip()
                pdf_path = ""
                if result.returncode == 0 and output:
                    try:
                        pdf_result = json.loads(output)
                        pdf_path = pdf_result.get("pdf_path", "")
                    except json.JSONDecodeError:
                        pass

                # Update pdf_path in entry
                if pdf_path:
                    if field == "resume":
                        app["pdf_path"] = pdf_path
                        app["resume"] = tex_path
                    elif field == "cover_letter":
                        app["cover_letter"] = tex_path

                if result.returncode != 0:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "ok": True,
                        "error": result.stderr[:500],
                        "pdf_path": "",
                    }).encode())
                    return

            # Save updated apps back to disk
            APP_FILE.write_text(json.dumps(apps, indent=2))

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "tex_path": tex_path,
                "pdf_path": app.get("pdf_path", ""),
            }).encode())

        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _discover_jobs(self):
        """
        POST /api/discover
        Body: { "mode": "7d"|"24h", "clear": true|false }

        Starts the discovery script in a background thread and returns
        immediately. The client polls GET /api/discover/status for progress.
        """
        import subprocess

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            mode = data.get("mode", "7d")
            clear = data.get("clear", False)

            if mode not in ("7d", "24h"):
                raise ValueError(f"Invalid mode: {mode}. Use '7d' or '24h'.")

            # Don't allow concurrent discovery runs
            with _discovery_lock:
                if _discovery_status["running"]:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "ok": False,
                        "error": "Discovery already in progress",
                    }).encode())
                    return
                _discovery_status["running"] = True
                _discovery_status["started_at"] = time.time()
                _discovery_status["jobs_found"] = 0
                _discovery_status["error"] = None

            thread = threading.Thread(
                target=_run_discovery, args=(mode, clear),
                daemon=True,
            )
            thread.start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "status": "running",
            }).encode())

        except Exception as e:
            with _discovery_lock:
                _discovery_status["running"] = False
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _discover_status(self):
        """GET /api/discover/status — returns current discovery state."""
        with _discovery_lock:
            status = dict(_discovery_status)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())

    def log_message(self, format, *args):
        """Suppress default logging noise."""
        if "/api/" in str(args[0]):
            print(f"  {args[0]}", flush=True)


# ── Discovery background runner ─────────────────────────────────────────────

def _run_discovery(mode, clear):
    """Run discover_jobs.py in a background daemon thread.

    Updates _discovery_status under lock when complete. Designed to be
    spawned by _discover_jobs() via threading.Thread.
    """
    import subprocess
    script = PROJECT_ROOT / "scripts" / "discover_jobs.py"
    try:
        if clear:
            _reset_queue_file()

        result = subprocess.run(
            [sys.executable, str(script), "--mode", mode],
            capture_output=True, text=True, timeout=600,
            cwd=str(PROJECT_ROOT),
        )

        if result.returncode != 0:
            with _discovery_lock:
                _discovery_status["error"] = (
                    result.stderr[:500] or result.stdout[:500]
                    or f"Exit code {result.returncode}"
                )
                _discovery_status["running"] = False
            return

        # Count jobs after discovery completes
        queue_file = DATA_DIR / "job_queue.html"
        jobs_found = 0
        if queue_file.exists():
            from scripts.discover_jobs import parse_existing_jobs
            jobs_found = len(parse_existing_jobs(queue_file))

        with _discovery_lock:
            _discovery_status["jobs_found"] = jobs_found
            _discovery_status["running"] = False
            _discovery_status["error"] = None

    except Exception as e:
        with _discovery_lock:
            _discovery_status["error"] = str(e)
            _discovery_status["running"] = False


# ── Module-level helpers (used by handlers and tests) ──

QUEUE_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
    <meta http-equiv="Pragma" content="no-cache" />
    <meta http-equiv="Expires" content="0" />
    <title>JobQuest — Discovery Queue</title>
    <style>
      * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }
      body {
        font-family:
          -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: #0d1117;
        color: #c9d1d9;
        padding: 20px;
      }
      h1 {
        font-size: 1.5em;
        margin-bottom: 16px;
        color: #58a6ff;
      }
      .toolbar {
        display: flex;
        gap: 12px;
        margin-bottom: 16px;
        flex-wrap: wrap;
        align-items: center;
      }
      .toolbar input,
      .toolbar select {
        background: #161b22;
        border: 1px solid #30363d;
        color: #c9d1d9;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 14px;
      }
      .toolbar input {
        width: 240px;
      }
      .stats {
        color: #8b949e;
        font-size: 13px;
        margin-left: auto;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
      }
      th {
        text-align: left;
        padding: 10px 12px;
        border-bottom: 1px solid #30363d;
        color: #8b949e;
        font-weight: 600;
        cursor: pointer;
        user-select: none;
        white-space: nowrap;
      }
      th:hover {
        color: #c9d1d9;
      }
      th .arrow {
        font-size: 10px;
        margin-left: 4px;
      }
      td {
        padding: 10px 12px;
        border-bottom: 1px solid #21262d;
      }
      tr:hover {
        background: #161b22;
      }
      a {
        color: #58a6ff;
        text-decoration: none;
      }
      a:hover {
        text-decoration: underline;
      }
      .tag {
        display: inline-block;
        padding: 1px 6px;
        border-radius: 8px;
        font-size: 11px;
        margin-left: 4px;
      }
      .tag-growth {
        background: #23863633;
        color: #3fb950;
        border: 1px solid #23863655;
      }
      .tag-ai {
        background: #6e40c933;
        color: #a371f7;
        border: 1px solid #6e40c955;
      }
      .tag-generalist {
        background: #9e6a0333;
        color: #d29922;
        border: 1px solid #9e6a0355;
      }
      .tag-de {
        background: #30363d;
        color: #8b949e;
      }
      .tag-es {
        background: #30363d;
        color: #8b949e;
      }
      .tag-remote {
        background: #1f6feb33;
        color: #79c0ff;
        border: 1px solid #1f6feb55;
      }
      .empty {
        text-align: center;
        padding: 40px;
        color: #484f58;
      }
      #move-btn {
        background: #1f6feb;
        border: none;
        color: white;
        padding: 6px 16px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 14px;
        display: none;
      }
      #move-btn:hover {
        background: #388bfd;
      }
      #move-btn.visible {
        display: inline-block;
      }
      .row-checkbox {
        width: 16px;
        height: 16px;
        cursor: pointer;
        accent-color: #1f6feb;
      }
      .select-all-checkbox {
        width: 16px;
        height: 16px;
        cursor: pointer;
        accent-color: #1f6feb;
      }
      .company-url-link {
        color: #79c0ff;
        font-size: 11px;
        margin-left: 6px;
        text-decoration: none;
      }
      .company-url-link:hover {
        text-decoration: underline;
      }
    </style>
  </head>
  <body>
    <h1>🔍 Job Discovery Queue</h1>

    <div class="toolbar">
      <input
        type="text"
        id="search"
        placeholder="Search..."
        oninput="render()"
      />
      <select id="role-filter" onchange="render()">
        <option value="">All roles</option>
        <option value="growth">Growth PM</option>
        <option value="ai">AI PM</option>
        <option value="generalist">Generalist PM</option>
      </select>
      <select id="country-filter" onchange="render()">
        <option value="">All countries</option>
        <option value="de">🇩🇪 Germany</option>
        <option value="es">🇪🇸 Spain</option>
      </select>
      <button id="move-btn" onclick="moveToTracker()">
        📋 Move Selected to Tracker
      </button>
      <button id="discover-btn" onclick="showDiscoveryModal()" style="background:#238636;border:none;color:white;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px;">
        🔍 Run Discovery
      </button>
      <span class="stats" id="stats"></span>
    </div>

    <table>
      <thead>
        <tr>
          <th style="width: 30px">
            <input
              type="checkbox"
              class="select-all-checkbox"
              id="select-all"
              onchange="toggleSelectAll()"
              title="Select all visible"
            />
          </th>
          <th onclick="sortBy('company')">
            Company <span class="arrow" id="arrow-company"></span>
          </th>
          <th onclick="sortBy('title')">
            Role <span class="arrow" id="arrow-title"></span>
          </th>
          <th onclick="sortBy('location')">
            Location <span class="arrow" id="arrow-location"></span>
          </th>
          <th onclick="sortBy('date')">
            Date <span class="arrow" id="arrow-date"></span>
          </th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="empty" id="empty" style="display: none">
      No jobs discovered yet.
    </div>

    <div id="discovery-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:200;align-items:center;justify-content:center;">
      <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:24px;width:420px;max-width:90vw;">
        <h3 style="color:#58a6ff;margin-bottom:16px;">🔍 Start Job Discovery</h3>
        <p style="color:#8b949e;font-size:13px;margin-bottom:16px;">
          Search for new PM job postings across the web.
        </p>
        <div style="margin-bottom:16px;">
          <label style="color:#c9d1d9;font-size:13px;font-weight:600;display:block;margin-bottom:6px;">Time range</label>
          <label style="color:#8b949e;font-size:13px;margin-right:16px;"><input type="radio" name="discover-mode" value="7d" checked> Last 7 days</label>
          <label style="color:#8b949e;font-size:13px;"><input type="radio" name="discover-mode" value="24h"> Last 24 hours</label>
        </div>
        <div style="margin-bottom:20px;">
          <label style="color:#c9d1d9;font-size:13px;font-weight:600;display:block;margin-bottom:6px;">Existing positions</label>
          <label style="color:#8b949e;font-size:13px;margin-right:16px;"><input type="radio" name="discover-clear" value="keep" checked> Keep</label>
          <label style="color:#8b949e;font-size:13px;"><input type="radio" name="discover-clear" value="remove"> Remove</label>
        </div>
        <div id="discover-status" style="color:#8b949e;font-size:12px;margin-bottom:12px;"></div>
        <div style="display:flex;gap:8px;">
          <button id="start-btn" onclick="startDiscovery()" style="background:#238636;border:none;color:white;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:14px;flex:1;">Start Discovery</button>
          <button id="cancel-btn" onclick="hideDiscoveryModal()" style="background:#30363d;border:none;color:#8b949e;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:14px;">Cancel</button>
        </div>
      </div>
    </div>

    <script>
      // JOBS DATA — populated by discovery, manually edited, or via agent
      const JOBS = [
    ];


      let sortCol = "date";
      let sortDir = -1;

      function roleTag(type) {
        const map = {
          growth: "tag-growth",
          ai: "tag-ai",
          generalist: "tag-generalist",
        };
        return `<span class="tag ${map[type] || ""}">${type}</span>`;
      }

      function render() {
        const search = document.getElementById("search").value.toLowerCase();
        const roleFilter = document.getElementById("role-filter").value;
        const countryFilter = document.getElementById("country-filter").value;

        let filtered = JOBS;
        if (search) {
          filtered = filtered.filter(
            (j) =>
              (j.company || "").toLowerCase().includes(search) ||
              (j.title || "").toLowerCase().includes(search) ||
              (j.location || "").toLowerCase().includes(search),
          );
        }
        if (roleFilter)
          filtered = filtered.filter((j) => j.roleType === roleFilter);
        if (countryFilter)
          filtered = filtered.filter((j) => j.country === countryFilter);

        filtered.sort((a, b) => {
          let va = a[sortCol] || "",
            vb = b[sortCol] || "";
          if (sortCol === "date") {
            va = va.toString();
            vb = vb.toString();
          }
          return va < vb ? -1 * sortDir : va > vb ? 1 * sortDir : 0;
        });

        document
          .querySelectorAll(".arrow")
          .forEach((el) => (el.textContent = ""));
        const arrow = document.getElementById("arrow-" + sortCol);
        if (arrow) arrow.textContent = sortDir === 1 ? "▲" : "▼";

        document.getElementById("stats").textContent =
          `${filtered.length} jobs`;

        const tbody = document.getElementById("tbody");
        if (filtered.length === 0) {
          tbody.innerHTML = "";
          document.getElementById("empty").style.display = "block";
          return;
        }
        document.getElementById("empty").style.display = "none";

        tbody.innerHTML = filtered
          .map(
            (j) => `
    <tr>
      <td><input type="checkbox" class="row-checkbox" data-idx="${JOBS.indexOf(j)}" onchange="updateMoveButton()"></td>
      <td><a href="${j.companyUrl || j.url}" target="_blank">${j.company || "?"}</a>${j.companyUrl ? `<a href="${j.url}" class="company-url-link" title="Board listing">🔗</a>` : ""} ${roleTag(j.roleType)}</td>
      <td>${j.title || "?"}</td>
      <td>${j.location || ""} ${j.country === "de" ? '<span class="tag tag-de">DE</span>' : ""}${j.country === "es" ? '<span class="tag tag-es">ES</span>' : ""}${(j.location || "").toLowerCase().includes("remote") ? '<span class="tag tag-remote">remote</span>' : ""}</td>
      <td>${j.date || ""}</td>
    </tr>
  `,
          )
          .join("");
      }

      function sortBy(col) {
        if (sortCol === col) {
          sortDir = -sortDir;
        } else {
          sortCol = col;
          sortDir = col === "date" ? -1 : 1;
        }
        render();
      }

      function toggleSelectAll() {
        const checked = document.getElementById("select-all").checked;
        document.querySelectorAll(".row-checkbox").forEach((cb) => {
          cb.checked = checked;
        });
        updateMoveButton();
      }

      function updateMoveButton() {
        const anyChecked =
          document.querySelectorAll(".row-checkbox:checked").length > 0;
        const btn = document.getElementById("move-btn");
        if (anyChecked) {
          btn.classList.add("visible");
          btn.textContent = `📋 Move Selected to Tracker (${document.querySelectorAll(".row-checkbox:checked").length})`;
        } else {
          btn.classList.remove("visible");
        }
      }

      // Normalize URL for dedup (strip hash, trailing slash)
      function normUrl(u) {
        try { const p = new URL(u); p.hash = ""; if (p.pathname.endsWith("/") && p.pathname !== "/") p.pathname = p.pathname.slice(0,-1); return p.toString(); }
        catch { return (u||"").replace(/#.*$/,"").replace(/\\/+$/,"") || u; }
      }

      async function moveToTracker() {
        const checked = document.querySelectorAll(".row-checkbox:checked");
        if (checked.length === 0) return;

        const toMove = [];
        const indicesToRemove = [];
        checked.forEach((cb) => {
          const idx = parseInt(cb.dataset.idx);
          if (idx >= 0 && idx < JOBS.length) {
            const job = JOBS[idx];
            toMove.push({
              company: job.company,
              role: job.title,
              url: job.companyUrl || job.url,
              date: job.date,
              status: "applied",
              notes: `Source: ${job.source} | Location: ${job.location}`,
            });
            indicesToRemove.push(idx);
          }
        });
        if (toMove.length === 0) return;

        try {
          const resp = await fetch("http://127.0.0.1:7878/api/applications");
          let existing = [];
          if (resp.ok) existing = await resp.json();

          // Check for URL duplicates
          const existingUrls = new Set(existing.map(a => normUrl(a.url || "")));
          const dupes = toMove.filter(j => existingUrls.has(normUrl(j.url)));
          if (dupes.length > 0) {
            const names = dupes.map(j => `${j.company} — ${j.role}`).join("\n  • ");
            const skip = !confirm(`⚠ ${dupes.length} job(s) already in tracker:\n  • ${names}\n\nSkip duplicates and save the rest?`);
            if (skip) return;
          }

          const newEntries = toMove.filter(j => !existingUrls.has(normUrl(j.url)));
          const merged = [...existing, ...newEntries];

          if (newEntries.length === 0) {
            alert("All selected jobs already exist in the tracker.");
            return;
          }

          const saveResp = await fetch("http://127.0.0.1:7878/api/applications", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(merged),
          });

          if (saveResp.ok) {
            indicesToRemove.sort((a, b) => b - a);
            indicesToRemove.forEach((idx) => JOBS.splice(idx, 1));
            document.getElementById("select-all").checked = false;
            updateMoveButton();
            render();
          } else {
            alert("Failed to save to tracker. Is the tracker server running? (python serve_tracker.py)");
          }
        } catch (e) {
          alert("Could not reach tracker server. Start it with: python serve_tracker.py");
        }
      }

      // ── Discovery Modal ──
      function showDiscoveryModal() {
        document.getElementById('discovery-modal').style.display = 'flex';
        document.getElementById('discover-status').textContent = '';
      }
      function hideDiscoveryModal() {
        document.getElementById('discovery-modal').style.display = 'none';
      }
      async function startDiscovery() {
        const mode = document.querySelector('input[name="discover-mode"]:checked').value;
        const clear = document.querySelector('input[name="discover-clear"]:checked').value === 'remove';
        const status = document.getElementById('discover-status');
        const startBtn = document.getElementById('start-btn');
        const cancelBtn = document.getElementById('cancel-btn');

        status.textContent = '⏳ Starting discovery...';
        status.style.color = '#8b949e';
        startBtn.disabled = true;
        cancelBtn.disabled = true;

        try {
          // 1. Kick off discovery (returns immediately)
          const resp = await fetch('/api/discover', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode, clear }),
          });
          const kickoff = await resp.json();

          if (!kickoff.ok) {
            status.textContent = `❌ ${kickoff.error || 'Discovery failed to start'}`;
            status.style.color = '#da3633';
            startBtn.disabled = false;
            cancelBtn.disabled = false;
            return;
          }

          // 2. Poll for completion
          let pollCount = 0;
          const poll = setInterval(async () => {
            pollCount++;
            try {
              const statusResp = await fetch('/api/discover/status');
              const s = await statusResp.json();

              if (s.error) {
                status.textContent = `❌ ${s.error}`;
                status.style.color = '#da3633';
                clearInterval(poll);
                startBtn.disabled = false;
                cancelBtn.disabled = false;
                return;
              }

              if (s.running) {
                const dots = '.'.repeat((pollCount % 3) + 1);
                status.textContent = `⏳ Searching${dots} (${Math.floor((Date.now()/1000 - s.started_at)/60)}m elapsed)`;
                return;
              }

              // Done — success
              status.textContent = `✅ Found ${s.jobs_found} jobs! Reloading...`;
              status.style.color = '#238636';
              clearInterval(poll);
              setTimeout(() => {
                hideDiscoveryModal();
                location.reload();
              }, 1500);
            } catch (e) {
              // Polling error — keep trying a few times
              if (pollCount > 30) {
                status.textContent = '⚠️ Lost connection to server. Check if the tracker is still running.';
                status.style.color = '#d29922';
                clearInterval(poll);
                startBtn.disabled = false;
                cancelBtn.disabled = false;
              }
            }
          }, 2000);
        } catch (e) {
          status.textContent = `❌ Error: ${e.message}. Is the tracker server running?`;
          status.style.color = '#da3633';
          startBtn.disabled = false;
          cancelBtn.disabled = false;
        }
      }

      // Auto-open modal on page load if query param ?discover is present, or just show the button
      // Show modal automatically on first load
      if (!sessionStorage.getItem('discovery-dismissed')) {
        showDiscoveryModal();
      }
      // Hide modal on Cancel also sets the flag
      const origHide = hideDiscoveryModal;
      hideDiscoveryModal = function() {
        sessionStorage.setItem('discovery-dismissed', 'true');
        origHide();
      };

      render();
    </script>
  </body>
</html>
"""


def _reset_queue_file():
    """Reset the job queue to an empty template."""
    queue_file = DATA_DIR / "job_queue.html"
    queue_file.write_text(QUEUE_TEMPLATE)


def main():
    parser = argparse.ArgumentParser(description="JobQuest Tracker Server")
    parser.add_argument("--port", type=int, default=7878, help="Port to listen on (default: 7878)")
    args = parser.parse_args()

    if not APP_FILE.exists():
        print(f"  Creating empty {APP_FILE}", flush=True)
        APP_FILE.write_text("[]")

    server = HTTPServer(("127.0.0.1", args.port), TrackerHandler)
    print(f"\n  📋 JobQuest Tracker → http://127.0.0.1:{args.port}\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()
