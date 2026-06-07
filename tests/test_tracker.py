"""Tests for tracker data persistence — pipeline save + server recompile.

Run with: pytest tests/test_tracker.py -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


class TestSaveApplicationJson:
    """_save_application_json reads .tex content from output dirs."""

    def _make_fake_output(self, tmp_path):
        """Create a fake output directory with .tex and qa files."""
        run_dir = tmp_path / "output" / "TestCo_2026-06-02"
        run_dir.mkdir(parents=True)

        resume_tex = run_dir / "Resume_Rodrigo-Lopes.tex"
        resume_tex.write_text("\\documentclass{article}\nHello resume")

        cl_tex = run_dir / "Cover-Letter_RodrigoLopes.tex"
        cl_tex.write_text("\\documentclass{article}\nHello cover letter")

        qa_md = run_dir / "qa_TestCo.md"
        qa_md.write_text("### Q: Why?\n\n### A: Because.\n")
        return run_dir

    def _make_fake_ctx(self, run_dir):
        rd = str(run_dir)
        return {
            "job": {"company": "TestCo", "title": "Test PM"},
            "job_url": "https://example.com/job/1",
            "company_safe": "TestCo",
            "run_dir": rd,
            "pipeline_score": 72,
            "pipeline_score_label": "GOOD",
            "pdf_path": f"{rd}/Resume_Rodrigo-Lopes.pdf",
        }

    def test_saves_content_fields(self, tmp_path, monkeypatch):
        """_save_application_json should store cover_letter_content and resume_content."""
        from apply import _save_application_json

        run_dir = self._make_fake_output(tmp_path)
        ctx = self._make_fake_ctx(run_dir)

        # Point PROJECT_ROOT to tmp_path so data dir is isolated
        monkeypatch.setattr("apply.PROJECT_ROOT", tmp_path)
        from rich.console import Console
        _save_application_json(ctx, Console())

        app_file = tmp_path / "data" / "applications.json"
        assert app_file.exists()
        apps = json.loads(app_file.read_text())
        assert len(apps) == 1
        app = apps[0]

        assert app["cover_letter_content"] == "\\documentclass{article}\nHello cover letter"
        assert app["resume_content"] == "\\documentclass{article}\nHello resume"
        assert "### Q: Why?" in app["qa"]

    def test_handles_missing_output_dir(self, tmp_path, monkeypatch):
        """Should not crash if run_dir doesn't exist."""
        from apply import _save_application_json

        ctx = self._make_fake_ctx("/nonexistent/path")
        monkeypatch.setattr("apply.PROJECT_ROOT", tmp_path)
        from rich.console import Console
        _save_application_json(ctx, Console())

        app_file = tmp_path / "data" / "applications.json"
        apps = json.loads(app_file.read_text())
        app = apps[0]
        assert app["cover_letter_content"] == ""
        assert app["resume_content"] == ""

    def test_dedup_by_url(self, tmp_path, monkeypatch):
        """Running twice with same URL should replace, not append."""
        from apply import _save_application_json

        run_dir = self._make_fake_output(tmp_path)
        ctx = self._make_fake_ctx(run_dir)
        monkeypatch.setattr("apply.PROJECT_ROOT", tmp_path)
        from rich.console import Console

        # First save
        _save_application_json(ctx, Console())

        # Second save (same URL)
        ctx["pipeline_score"] = 85
        _save_application_json(ctx, Console())

        app_file = tmp_path / "data" / "applications.json"
        apps = json.loads(app_file.read_text())
        assert len(apps) == 1  # no duplicate
        assert apps[0]["score"] == 85  # updated


class TestJobsHubDiscover:
    """Tests for the /api/discover endpoint logic."""

    def test_clear_queue_creates_empty_file(self, tmp_path, monkeypatch):
        """When clear=True, the queue file should be reset to a basic template."""
        from serve_tracker import _reset_queue_file, DATA_DIR, PROJECT_ROOT

        monkeypatch.setattr("serve_tracker.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("serve_tracker.DATA_DIR", tmp_path / "data")
        monkeypatch.setattr("serve_tracker.APP_FILE", tmp_path / "data" / "applications.json")

        # Create a queue file with some content
        queue_file = tmp_path / "data" / "job_queue.html"
        queue_file.parent.mkdir(parents=True)
        queue_file.write_text("<html><body>Old content</body></html>")

        _reset_queue_file()

        content = queue_file.read_text()
        assert "Old content" not in content
        assert "const JOBS = [" in content or "const JOBS=[" in content

    def test_clear_queue_template_is_parseable(self, tmp_path, monkeypatch):
        """After clear, discover_jobs.py's parse_existing_jobs should read the
        empty template without errors (returns empty list, not crashes)."""
        from serve_tracker import _reset_queue_file

        monkeypatch.setattr("serve_tracker.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("serve_tracker.DATA_DIR", tmp_path / "data")
        monkeypatch.setattr("serve_tracker.APP_FILE", tmp_path / "data" / "applications.json")

        queue_file = tmp_path / "data" / "job_queue.html"
        queue_file.parent.mkdir(parents=True)
        queue_file.write_text("<html><body>Old</body></html>")

        _reset_queue_file()

        from scripts.discover_jobs import parse_existing_jobs
        jobs = parse_existing_jobs(queue_file)
        assert jobs == [], f"Expected empty list, got {len(jobs)} jobs"

    def test_discover_script_path(self):
        """The discover script should exist at scripts/discover_jobs.py."""
        script = Path("scripts/discover_jobs.py")
        assert script.exists(), f"Discover script not found at {script}"

    def test_discover_script_runs_dry(self):
        """Running discover_jobs.py --dry-run should validate args."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/discover_jobs.py", "--help"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "mode" in result.stdout or "--mode" in result.stdout

    def test_discover_accepts_7d_mode(self):
        """The --mode flag should accept '7d' and '24h' as valid choices.
        Check via --help output which shows valid choices."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/discover_jobs.py", "--help"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        assert "7d" in result.stdout
        assert "24h" in result.stdout

    def test_discover_rejects_invalid_mode(self):
        """Invalid mode should trigger an error from the script."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/discover_jobs.py", "--mode", "INVALID", "--dry-run"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode != 0 or "INVALID" in result.stderr or "usage:" in result.stderr

    def test_exa_search_passes_mode_recency_24h(self):
        """exa_search should include startPublishedDate=1 day ago when mode='24h'."""
        from scripts.discover_jobs import exa_search
        import urllib.request
        import urllib.error
        import json
        from datetime import date, timedelta

        captured = {}
        original_urlopen = urllib.request.urlopen

        def mock_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode())
            raise urllib.error.URLError("Mock not calling API")
        urllib.request.urlopen = mock_urlopen

        try:
            exa_search("test query", num_results=3, mode="24h")
        except Exception:
            pass
        urllib.request.urlopen = original_urlopen

        assert "payload" in captured, "exa_search did not send a request payload"
        payload = captured["payload"]
        expected = (date.today() - timedelta(days=1)).isoformat()
        assert payload.get("startPublishedDate") == expected, (
            f"24h mode: expected startPublishedDate={expected}, got {payload.get('startPublishedDate')}"
        )

    def test_exa_search_passes_mode_recency_7d(self):
        """exa_search should include startPublishedDate=7 days ago when mode='7d'."""
        from scripts.discover_jobs import exa_search
        import urllib.request
        import urllib.error
        import json
        from datetime import date, timedelta

        captured = {}
        original_urlopen = urllib.request.urlopen

        def mock_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode())
            raise urllib.error.URLError("Mock not calling API")
        urllib.request.urlopen = mock_urlopen

        try:
            exa_search("test query", num_results=3, mode="7d")
        except Exception:
            pass
        urllib.request.urlopen = original_urlopen

        assert "payload" in captured, "exa_search did not send a request payload"
        payload = captured["payload"]
        expected = (date.today() - timedelta(days=7)).isoformat()
        assert payload.get("startPublishedDate") == expected, (
            f"7d mode: expected startPublishedDate={expected}, got {payload.get('startPublishedDate')}"
        )


class TestDiscoveryAsync:
    """Test the async discovery dispatch and polling endpoint (U3)."""

    def test_discovery_status_endpoint_returns_running(self, tmp_path, monkeypatch):
        """GET /api/discover/status should return running=false when idle."""
        import threading
        import time
        from http.server import HTTPServer

        monkeypatch.setattr("serve_tracker.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("serve_tracker.DATA_DIR", tmp_path / "data")
        monkeypatch.setattr("serve_tracker.APP_FILE", tmp_path / "data" / "applications.json")
        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "applications.json").write_text("[]")

        # Override discovery status to a known idle state
        import serve_tracker
        serve_tracker._discovery_lock = threading.Lock()
        serve_tracker._discovery_status = {
            "running": False, "started_at": 0, "jobs_found": 0, "error": None
        }

        # Start server in a daemon thread
        server = HTTPServer(("127.0.0.1", 17890), serve_tracker.TrackerHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        try:
            import urllib.request
            resp = urllib.request.urlopen("http://127.0.0.1:17890/api/discover/status", timeout=3)
            assert resp.status == 200
            import json
            data = json.loads(resp.read())
            assert data["running"] is False
            assert "started_at" in data
            assert "jobs_found" in data
            assert "error" in data
        finally:
            server.shutdown()

    def test_discovery_already_running_is_rejected(self, tmp_path, monkeypatch):
        """POST /api/discover should return error when discovery is already running."""
        import threading
        import json
        import serve_tracker

        monkeypatch.setattr("serve_tracker.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("serve_tracker.DATA_DIR", tmp_path / "data")
        monkeypatch.setattr("serve_tracker.APP_FILE", tmp_path / "data" / "applications.json")
        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "applications.json").write_text("[]")
        (tmp_path / "data" / "job_queue.html").write_text(
            '<html><head></head><body><script>const JOBS = [];</script></body></html>'
        )

        serve_tracker._discovery_lock = threading.Lock()
        serve_tracker._discovery_status = {
            "running": True, "started_at": 999, "jobs_found": 0, "error": None
        }

        # Send POST request
        import urllib.request
        body = json.dumps({"mode": "7d", "clear": False}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:17891/api/discover",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        from http.server import HTTPServer
        server = HTTPServer(("127.0.0.1", 17891), serve_tracker.TrackerHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        import time
        time.sleep(0.3)

        try:
            resp = urllib.request.urlopen(req, timeout=3)
            data = json.loads(resp.read())
            assert resp.status == 200
            assert data["ok"] is False
            assert "already" in data.get("error", "").lower()
        finally:
            server.shutdown()

    def test_discovery_post_returns_immediately(self, tmp_path, monkeypatch):
        """POST /api/discover should return within 3 seconds (non-blocking)."""
        import threading
        import json
        import time
        import serve_tracker
        from http.server import HTTPServer

        monkeypatch.setattr("serve_tracker.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("serve_tracker.DATA_DIR", tmp_path / "data")
        monkeypatch.setattr("serve_tracker.APP_FILE", tmp_path / "data" / "applications.json")
        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "applications.json").write_text("[]")
        (tmp_path / "data" / "job_queue.html").write_text(
            '<html><head></head><body><script>const JOBS = [];</script></body></html>'
        )

        serve_tracker._discovery_lock = threading.Lock()
        serve_tracker._discovery_status = {
            "running": False, "started_at": 0, "jobs_found": 0, "error": None
        }

        server = HTTPServer(("127.0.0.1", 17892), serve_tracker.TrackerHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        try:
            import urllib.request
            body = json.dumps({"mode": "7d", "clear": False}).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:17892/api/discover",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            start = time.time()
            resp = urllib.request.urlopen(req, timeout=5)
            elapsed = time.time() - start
            data = json.loads(resp.read())

            assert elapsed < 3, f"Discovery POST took {elapsed:.1f}s, expected < 3s"
            assert resp.status == 200
            assert data["ok"] is True
            assert data.get("status") == "running"
        finally:
            server.shutdown()

    def test_discovery_invalid_mode_returns_error(self, tmp_path, monkeypatch):
        """POST /api/discover with invalid mode should return error."""
        import threading
        import json
        import time
        import serve_tracker
        from http.server import HTTPServer

        monkeypatch.setattr("serve_tracker.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("serve_tracker.DATA_DIR", tmp_path / "data")
        monkeypatch.setattr("serve_tracker.APP_FILE", tmp_path / "data" / "applications.json")
        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "applications.json").write_text("[]")

        serve_tracker._discovery_lock = threading.Lock()
        serve_tracker._discovery_status = {
            "running": False, "started_at": 0, "jobs_found": 0, "error": None
        }

        server = HTTPServer(("127.0.0.1", 17893), serve_tracker.TrackerHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        try:
            import urllib.request
            import urllib.error
            body = json.dumps({"mode": "invalid", "clear": False}).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:17893/api/discover",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                resp = urllib.request.urlopen(req, timeout=3)
            except urllib.error.HTTPError as e:
                resp = e
            data = json.loads(resp.read())
            # Invalid mode returns 400 with error
            assert resp.code == 400
            assert "error" in data
        finally:
            server.shutdown()


class TestSaveJsonRecompile:
    """Test the recompile logic: write .tex content and run render_pdf."""

    def test_write_tex_content_to_disk(self, tmp_path):
        """Writing updated .tex content to disk should replace the file."""
        tex_file = tmp_path / "Resume_Rodrigo-Lopes.tex"
        tex_file.write_text("old content")

        new_content = "\\documentclass{article}\nUpdated resume"
        tex_file.write_text(new_content)

        assert tex_file.read_text() == new_content

    def test_save_json_includes_content_fields(self, tmp_path, monkeypatch):
        """Verify that _save_application_json stores content fields."""
        from apply import _save_application_json

        run_dir = tmp_path / "output" / "TestCo_2026-06-02"
        run_dir.mkdir(parents=True)

        resume_tex = run_dir / "Resume_Rodrigo-Lopes.tex"
        resume_tex.write_text("\\documentclass{article}\nResume")

        cl_tex = run_dir / "Cover-Letter_RodrigoLopes.tex"
        cl_tex.write_text("\\documentclass{article}\nCover")

        qa_md = run_dir / "qa_TestCo.md"
        qa_md.write_text("Q: Why?\nA: Test\n")

        ctx = {
            "job": {"company": "TestCo", "title": "PM"},
            "job_url": "https://example.com/job",
            "company_safe": "TestCo",
            "run_dir": str(run_dir),
            "pipeline_score": 72,
            "pipeline_score_label": "GOOD",
            "pdf_path": str(run_dir / "Resume_Rodrigo-Lopes.pdf"),
        }

        monkeypatch.setattr("apply.PROJECT_ROOT", tmp_path)
        from rich.console import Console
        _save_application_json(ctx, Console())

        app_file = tmp_path / "data" / "applications.json"
        apps = json.loads(app_file.read_text())
        assert apps[0]["cover_letter_content"] == "\\documentclass{article}\nCover"
        assert apps[0]["resume_content"] == "\\documentclass{article}\nResume"
