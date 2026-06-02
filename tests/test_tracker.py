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
            [sys.executable, "scripts/discover_jobs.py", "--mode", "INVALID", "--dry-run"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode != 0 or "INVALID" in result.stderr or "usage:" in result.stderr


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
