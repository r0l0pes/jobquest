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
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
APP_FILE = DATA_DIR / "applications.json"


class TrackerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/applications":
            self._serve_json()
        elif self.path.startswith("/api/check-url"):
            self._check_url()
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

        Runs scripts/discover_jobs.py with the given mode.
        If clear is true, resets the queue file before running.
        """
        import subprocess
        from io import StringIO

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            mode = data.get("mode", "7d")
            clear = data.get("clear", False)

            if mode not in ("7d", "24h"):
                raise ValueError(f"Invalid mode: {mode}. Use '7d' or '24h'.")

            # Optionally clear the queue
            if clear:
                _reset_queue_file()

            # Run the discovery script
            script = PROJECT_ROOT / "scripts" / "discover_jobs.py"
            if not script.exists():
                raise FileNotFoundError(f"Discovery script not found: {script}")

            result = subprocess.run(
                [sys.executable, str(script), "--mode", mode],
                capture_output=True, text=True, timeout=180,
                cwd=str(PROJECT_ROOT),
            )

            if result.returncode != 0:
                error_msg = result.stderr[:500] or result.stdout[:500] or f"Exit code {result.returncode}"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "ok": False,
                    "error": error_msg,
                }).encode())
                return

            # Count jobs by parsing the updated queue file
            queue_file = DATA_DIR / "job_queue.html"
            jobs_found = 0
            if queue_file.exists():
                import re
                content = queue_file.read_text()
                jobs_found = content.count('"company":')

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "jobs_found": jobs_found,
            }).encode())

        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, format, *args):
        """Suppress default logging noise."""
        if "/api/" in str(args[0]):
            print(f"  {args[0]}", flush=True)


# ── Module-level helpers (used by handlers and tests) ──

QUEUE_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>JobQuest — Discovery Queue</title>
  </head>
  <body>
    <p>Queue cleared. Run discovery again.</p>
  </body>
</html>"""


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
