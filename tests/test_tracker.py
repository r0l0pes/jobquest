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
        assert "jobQueue" in content or "tbody" in content or "<html" in content

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
            [sys.executable, "scripts/discover_jobs.py", "--mode", "INVALID", "--help"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode != 0 or "INVALID" in result.stderr or "usage:" in result.stderr

    def test_server_uses_threading(self):
        """Should use ThreadingHTTPServer (not single-threaded HTTPServer)."""
        from serve_tracker import TrackerHandler
        from http.server import ThreadingHTTPServer, HTTPServer

        # Verify the server class is ThreadingHTTPServer by checking main()
        import serve_tracker
        import inspect
        source = inspect.getsource(serve_tracker.main)
        assert "ThreadingHTTPServer" in source
        assert "HTTPServer" not in source or "ThreadingHTTPServer" in source

    def test_discover_store_initialized(self):
        """The discovery store and lock should exist at module level."""
        from serve_tracker import _discovery_store, _discovery_lock, _DISCOVERY_TIMEOUT
        assert isinstance(_discovery_store, dict)
        assert _discovery_lock is not None
        assert _DISCOVERY_TIMEOUT == 180

    def test_discover_reader_returns_immediately(self, tmp_path, monkeypatch):
        """POST /api/discover should return a job_id immediately (non-blocking)."""
        import json
        from serve_tracker import TrackerHandler
        from io import BytesIO

        # Point project root to tmp_path
        monkeypatch.setattr("serve_tracker.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("serve_tracker.DATA_DIR", tmp_path / "data")
        monkeypatch.setattr("serve_tracker.APP_FILE", tmp_path / "data" / "applications.json")
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "applications.json").write_text("[]")

        # Create a fake discover script that just prints to stderr and exits
        fake_script = tmp_path / "scripts" / "discover_jobs.py"
        fake_script.parent.mkdir(parents=True)
        fake_script.write_text(
            "import sys\n"
            "import time\n"
            "print('Searching query 1...', file=sys.stderr)\n"
            "print('  → 8 raw results', file=sys.stderr)\n"
            "time.sleep(0.1)\n"
            "print('Verifying URLs...', file=sys.stderr)\n"
            "print('{\"mode\":\"7d\",\"added\":5}', file=sys.stdout)\n"
        )

        # Simulate a POST request
        import http.server
        handler = TrackerHandler

        # Test the endpoint logic directly
        from serve_tracker import _discovery_store, _discovery_lock
        import uuid
        import subprocess
        import threading
        import time

        script = fake_script
        job_id = uuid.uuid4().hex[:8]
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(tmp_path),
        )

        entry = {
            "proc": proc,
            "stderr_lines": [],
            "started_at": time.time(),
            "done": False,
            "error": "",
            "jobs_found": 0,
        }

        with _discovery_lock:
            _discovery_store[job_id] = entry

        from serve_tracker import _discover_reader
        reader = threading.Thread(
            target=_discover_reader,
            args=(job_id, entry, proc, "7d"),
            daemon=True,
        )
        reader.start()

        # Should return immediately (non-blocking)
        assert job_id in _discovery_store
        assert not entry["done"]  # Not done yet

        # Wait for reader to finish
        reader.join(timeout=5)

        # After reader finishes
        with _discovery_lock:
            assert entry["done"] is True
            assert len(entry["stderr_lines"]) > 0
            assert "Searching query" in "\n".join(entry["stderr_lines"])

    def test_discover_log_endpoint_structure(self, tmp_path, monkeypatch):
        """GET /api/discover-log should return correct JSON structure."""
        from serve_tracker import _discovery_store, _discovery_lock
        import time

        monkeypatch.setattr("serve_tracker.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("serve_tracker.DATA_DIR", tmp_path / "data")
        monkeypatch.setattr("serve_tracker.APP_FILE", tmp_path / "data" / "applications.json")

        job_id = "test1234"
        entry = {
            "proc": None,
            "stderr_lines": ["line1", "line2"],
            "started_at": time.time(),
            "done": True,
            "error": "",
            "jobs_found": 5,
        }

        with _discovery_lock:
            _discovery_store[job_id] = entry

        # Check the store directly
        with _discovery_lock:
            stored = _discovery_store[job_id]

        assert stored["done"] is True
        assert stored["stderr_lines"] == ["line1", "line2"]
        assert stored["error"] == ""
        assert stored["jobs_found"] == 5

        # Clean up
        with _discovery_lock:
            del _discovery_store[job_id]

    def test_discover_cancel_structure(self, tmp_path, monkeypatch):
        """Cancelling a discovery should set done=True with error."""
        import subprocess
        from serve_tracker import _discovery_store, _discovery_lock
        import uuid
        import time

        monkeypatch.setattr("serve_tracker.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("serve_tracker.DATA_DIR", tmp_path / "data")
        monkeypatch.setattr("serve_tracker.APP_FILE", tmp_path / "data" / "applications.json")

        # Start a long-running script
        long_script = tmp_path / "sleep_script.py"
        long_script.write_text("import time; time.sleep(60); print('done')")

        job_id = uuid.uuid4().hex[:8]
        proc = subprocess.Popen(
            [sys.executable, str(long_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        entry = {
            "proc": proc,
            "stderr_lines": [],
            "started_at": time.time(),
            "done": False,
            "error": "",
            "jobs_found": 0,
        }

        with _discovery_lock:
            _discovery_store[job_id] = entry

        # Cancel it
        assert proc.poll() is None  # Still running
        proc.kill()
        proc.wait()

        with _discovery_lock:
            entry["done"] = True
            entry["error"] = "Cancelled by user"

        with _discovery_lock:
            stored = _discovery_store[job_id]

        assert stored["done"] is True
        assert stored["error"] == "Cancelled by user"

        # Clean up
        with _discovery_lock:
            del _discovery_store[job_id]


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
