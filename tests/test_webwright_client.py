"""Tests for Webwright client fallback module.

Mocks Webwright availability since the dependency may not be installed.
Tests the cache logic, script generation, and graceful degradation.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.webwright_client import (
    run_webwright_fallback,
    clear_script_cache,
    _compute_domain_hash,
    _inject_review_pause,
    _check_webwright_available,
    SCRIPT_CACHE_DIR,
)


class TestWebwrightAvailability:
    """Test graceful degradation when Webwright is not installed."""

    def test_returns_graceful_error_when_webwright_missing(self):
        """When Webwright is not installed, return a clear error message."""
        with patch("modules.webwright_client._check_webwright_available", return_value=False):
            result = run_webwright_fallback(
                job_url="https://example.com/jobs/123",
                resume_pdf="/path/to/resume.pdf",
                form_data_path="/path/to/form_data.json",
            )

        assert result["success"] is False
        assert "Webwright not installed" in result["error"]

    def test_check_webwright_available_when_installed(self):
        """When Webwright is importable, return True."""
        with patch.dict("sys.modules", {"webwright": MagicMock()}):
            assert _check_webwright_available() is True

    def test_check_webwright_available_when_missing(self):
        """When Webwright is not importable, return False."""
        with patch.dict("sys.modules", {"webwright": None}, clear=False):
            # Force re-import by clearing the import cache
            if "modules.webwright_client" in sys.modules:
                del sys.modules["modules.webwright_client"]
            from modules.webwright_client import _check_webwright_available
            assert _check_webwright_available() is False


class TestDomainHash:
    """Test cache key computation."""

    def test_same_url_same_hash(self):
        """Same URL should produce the same hash."""
        url = "https://boards.greenhouse.io/example/jobs/12345"
        h1 = _compute_domain_hash(url)
        h2 = _compute_domain_hash(url)
        assert h1 == h2
        assert len(h1) == 16  # truncated SHA-256

    def test_different_urls_different_hashes(self):
        """Different URLs should produce different hashes."""
        h1 = _compute_domain_hash("https://a.com/jobs/1")
        h2 = _compute_domain_hash("https://b.com/jobs/1")
        assert h1 != h2

    def test_path_prefix_included(self):
        """Different paths on same domain should produce different hashes."""
        h1 = _compute_domain_hash("https://example.com/jobs/1")
        h2 = _compute_domain_hash("https://example.com/jobs/2")
        assert h1 != h2


class TestScriptCache:
    """Test script caching behavior."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_script_cache()

    def teardown_method(self):
        """Clear cache after each test."""
        clear_script_cache()

    def test_cache_miss_generates_new_script(self):
        """When no cached script exists, attempt generation."""
        with patch("modules.webwright_client._check_webwright_available", return_value=True):
            with patch("modules.webwright_client._generate_script") as mock_gen:
                mock_gen.return_value = {
                    "success": True,
                    "script": "print('test script')",
                    "error": None,
                }

                result = run_webwright_fallback(
                    job_url="https://example.com/jobs/123",
                    resume_pdf="/path/to/resume.pdf",
                    form_data_path="/path/to/form_data.json",
                )

        mock_gen.assert_called_once()
        # Script should be saved to cache
        domain_hash = _compute_domain_hash("https://example.com/jobs/123")
        cached = SCRIPT_CACHE_DIR / f"{domain_hash}.py"
        assert cached.exists()

    def test_cache_hit_uses_cached_script(self):
        """When cached script exists, reuse without generation."""
        domain_hash = _compute_domain_hash("https://example.com/jobs/456")
        cached = SCRIPT_CACHE_DIR / f"{domain_hash}.py"
        cached.write_text("print('cached script')")

        with patch("modules.webwright_client._check_webwright_available", return_value=True):
            with patch("modules.webwright_client._generate_script") as mock_gen:
                with patch("modules.webwright_client._execute_script") as mock_exec:
                    mock_exec.return_value = {
                        "success": True,
                        "report": {"filled": 5},
                        "error": None,
                    }

                    result = run_webwright_fallback(
                        job_url="https://example.com/jobs/456",
                        resume_pdf="/path/to/resume.pdf",
                        form_data_path="/path/to/form_data.json",
                    )

        mock_gen.assert_not_called()  # Should not regenerate
        mock_exec.assert_called_once()
        assert result["success"] is True

    def test_clear_script_cache_removes_all(self):
        """clear_script_cache should remove all .py files in cache dir."""
        (SCRIPT_CACHE_DIR / "test1.py").write_text("test")
        (SCRIPT_CACHE_DIR / "test2.py").write_text("test")

        count = clear_script_cache()
        assert count == 2
        assert len(list(SCRIPT_CACHE_DIR.glob("*.py"))) == 0


class TestReviewPauseInjection:
    """Test that human-review pause is injected into scripts."""

    def test_injects_pause_before_browser_close(self):
        """Pause code should be inserted before browser.close()."""
        script = "# some code\nbrowser.close()"
        result = _inject_review_pause(script)

        assert "REVIEW THE FORM IN THE BROWSER" in result
        assert "Press Enter to close the browser" in result
        assert result.index("REVIEW") < result.index("browser.close()")

    def test_appends_pause_when_no_browser_close(self):
        """If script has no browser.close(), append pause at end."""
        script = "print('hello')"
        result = _inject_review_pause(script)

        assert "REVIEW THE FORM IN THE BROWSER" in result
        assert result.endswith("\n")  # appended at end


class TestScriptExecution:
    """Test script execution and error handling."""

    def test_script_timeout_returns_error(self):
        """If script times out, return graceful error."""
        with patch("modules.webwright_client.subprocess.run") as mock_run:
            from subprocess import TimeoutExpired
            mock_run.side_effect = TimeoutExpired(cmd="test", timeout=300)

            from modules.webwright_client import _execute_script
            result = _execute_script(
                Path("/fake/script.py"),
                "https://example.com",
                None,
                None,
            )

        assert result["success"] is False
        assert "timed out" in result["error"]

    def test_script_failure_returns_error(self):
        """If script exits non-zero, capture error."""
        with patch("modules.webwright_client.subprocess.run") as mock_run:
            mock_process = MagicMock()
            mock_process.returncode = 1
            mock_process.stdout = "{}"
            mock_process.stderr = "Error: page not found"
            mock_run.return_value = mock_process

            from modules.webwright_client import _execute_script
            result = _execute_script(
                Path("/fake/script.py"),
                "https://example.com",
                None,
                None,
            )

        assert result["success"] is False
        assert result["report"] is not None  # Should include whatever output we got

    def test_script_success_returns_report(self):
        """If script exits 0 with JSON, return parsed report."""
        with patch("modules.webwright_client.subprocess.run") as mock_run:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stdout = '{"filled": 5, "url": "https://example.com"}'
            mock_process.stderr = ""
            mock_run.return_value = mock_process

            from modules.webwright_client import _execute_script
            result = _execute_script(
                Path("/fake/script.py"),
                "https://example.com",
                None,
                None,
            )

        assert result["success"] is True
        assert result["report"]["filled"] == 5
