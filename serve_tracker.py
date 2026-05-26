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
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/applications":
            self._save_json()
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

    def log_message(self, format, *args):
        """Suppress default logging noise."""
        if "/api/" in str(args[0]):
            print(f"  {args[0]}", flush=True)


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
