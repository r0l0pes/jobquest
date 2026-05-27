"""Tests for form filler cascade logic.

TDD approach: test the orchestration layer that runs deterministic filler first,
then escalates to Webwright fallback when needed.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestFormFillerCascade:
    """Test the cascade orchestration logic."""

    def test_deterministic_succeeds_no_escalation(self):
        """Happy path: deterministic filler fills all fields, no escalation needed."""
        from modules.form_filler_cascade import run_cascade

        # Mock a successful deterministic run
        mock_report = {
            "url": "https://example.com/jobs/123",
            "resume_uploaded": True,
            "pages_filled": 1,
            "reports": [
                {
                    "page": 1,
                    "filled": [
                        {"label": "Full Name", "name": "name", "classified_as": "name"},
                        {"label": "Email", "name": "email", "classified_as": "email"},
                    ],
                    "skipped": [],
                    "unknown": [],
                }
            ],
            "summary": {"total_filled": 2, "total_skipped": 0, "total_unknown": 0},
        }

        with patch("modules.form_filler_cascade._run_deterministic") as mock_det:
            mock_det.return_value = (mock_report, 0)  # report, exit_code

            result = run_cascade(
                job_url="https://example.com/jobs/123",
                resume_pdf="/path/to/resume.pdf",
                form_data_path="/path/to/form_data.json",
            )

        assert result["escalated"] is False
        assert result["report"] == mock_report
        assert result["fallback_used"] is False

    def test_escalation_when_unknown_fields_exceed_threshold(self):
        """Escalate to Webwright when unknown fields > 3."""
        from modules.form_filler_cascade import run_cascade, ESCALATION_UNKNOWN_THRESHOLD

        mock_report = {
            "url": "https://example.com/jobs/123",
            "resume_uploaded": True,
            "pages_filled": 1,
            "reports": [
                {
                    "page": 1,
                    "filled": [{"label": "Name", "classified_as": "name"}],
                    "skipped": [],
                    "unknown": [
                        {"label": "Weird Field 1", "classified_as": "unknown"},
                        {"label": "Weird Field 2", "classified_as": "unknown"},
                        {"label": "Weird Field 3", "classified_as": "unknown"},
                        {"label": "Weird Field 4", "classified_as": "unknown"},
                    ],
                }
            ],
            "summary": {
                "total_filled": 1,
                "total_skipped": 0,
                "total_unknown": ESCALATION_UNKNOWN_THRESHOLD + 1,
            },
        }

        with patch("modules.form_filler_cascade._run_deterministic") as mock_det:
            with patch("modules.form_filler_cascade._run_webwright_fallback") as mock_fallback:
                mock_det.return_value = (mock_report, 0)
                mock_fallback.return_value = {"success": True, "filled_fields": 4}

                result = run_cascade(
                    job_url="https://example.com/jobs/123",
                    resume_pdf="/path/to/resume.pdf",
                    form_data_path="/path/to/form_data.json",
                )

        assert result["escalated"] is True
        assert result["fallback_used"] is True
        mock_fallback.assert_called_once()

    def test_escalation_when_resume_upload_fails(self):
        """Escalate when deterministic filler fails to upload resume."""
        from modules.form_filler_cascade import run_cascade

        mock_report = {
            "url": "https://example.com/jobs/123",
            "resume_uploaded": False,
            "pages_filled": 1,
            "reports": [
                {
                    "page": 1,
                    "filled": [{"label": "Name", "classified_as": "name"}],
                    "skipped": [],
                    "unknown": [],
                }
            ],
            "summary": {"total_filled": 1, "total_skipped": 0, "total_unknown": 0},
        }

        with patch("modules.form_filler_cascade._run_deterministic") as mock_det:
            with patch("modules.form_filler_cascade._run_webwright_fallback") as mock_fallback:
                mock_det.return_value = (mock_report, 0)
                mock_fallback.return_value = {"success": True, "filled_fields": 1}

                result = run_cascade(
                    job_url="https://example.com/jobs/123",
                    resume_pdf="/path/to/resume.pdf",
                    form_data_path="/path/to/form_data.json",
                )

        assert result["escalated"] is True
        assert result["fallback_used"] is True
        mock_fallback.assert_called_once()

    def test_no_escalation_at_exact_threshold(self):
        """Boundary: exactly at threshold should NOT escalate."""
        from modules.form_filler_cascade import run_cascade, ESCALATION_UNKNOWN_THRESHOLD

        unknown_fields = [
            {"label": f"Field {i}", "classified_as": "unknown"}
            for i in range(ESCALATION_UNKNOWN_THRESHOLD)
        ]
        mock_report = {
            "url": "https://example.com/jobs/123",
            "resume_uploaded": True,
            "pages_filled": 1,
            "reports": [
                {
                    "page": 1,
                    "filled": [],
                    "skipped": [],
                    "unknown": unknown_fields,
                }
            ],
            "summary": {
                "total_filled": 0,
                "total_skipped": 0,
                "total_unknown": ESCALATION_UNKNOWN_THRESHOLD,
            },
        }

        with patch("modules.form_filler_cascade._run_deterministic") as mock_det:
            mock_det.return_value = (mock_report, 0)

            result = run_cascade(
                job_url="https://example.com/jobs/123",
                resume_pdf="/path/to/resume.pdf",
                form_data_path="/path/to/form_data.json",
            )

        assert result["escalated"] is False
        assert result["fallback_used"] is False

    def test_escalation_when_deterministic_crashes(self):
        """Escalate to Webwright when deterministic filler crashes."""
        from modules.form_filler_cascade import run_cascade

        with patch("modules.form_filler_cascade._run_deterministic") as mock_det:
            with patch("modules.form_filler_cascade._run_webwright_fallback") as mock_fallback:
                mock_det.return_value = ({}, 1)  # empty report, non-zero exit
                mock_fallback.return_value = {"success": True, "filled_fields": 2}

                result = run_cascade(
                    job_url="https://example.com/jobs/123",
                    resume_pdf="/path/to/resume.pdf",
                    form_data_path="/path/to/form_data.json",
                )

        assert result["escalated"] is True
        assert result["fallback_used"] is True
        mock_fallback.assert_called_once()

    def test_no_webwright_flag_skips_fallback(self):
        """--no-webwright flag should force deterministic-only mode."""
        from modules.form_filler_cascade import run_cascade

        mock_report = {
            "url": "https://example.com/jobs/123",
            "resume_uploaded": False,  # Would normally trigger escalation
            "pages_filled": 1,
            "reports": [
                {
                    "page": 1,
                    "filled": [],
                    "skipped": [],
                    "unknown": [],
                }
            ],
            "summary": {"total_filled": 0, "total_skipped": 0, "total_unknown": 0},
        }

        with patch("modules.form_filler_cascade._run_deterministic") as mock_det:
            mock_det.return_value = (mock_report, 0)

            result = run_cascade(
                job_url="https://example.com/jobs/123",
                resume_pdf="/path/to/resume.pdf",
                form_data_path="/path/to/form_data.json",
                no_webwright=True,
            )

        assert result["escalated"] is False
        assert result["fallback_used"] is False

    def test_graceful_failure_when_both_paths_fail(self):
        """If both deterministic and fallback fail, return graceful error report."""
        from modules.form_filler_cascade import run_cascade

        with patch("modules.form_filler_cascade._run_deterministic") as mock_det:
            with patch("modules.form_filler_cascade._run_webwright_fallback") as mock_fallback:
                mock_det.return_value = ({}, 1)
                mock_fallback.return_value = {"success": False, "error": "Webwright failed"}

                result = run_cascade(
                    job_url="https://example.com/jobs/123",
                    resume_pdf="/path/to/resume.pdf",
                    form_data_path="/path/to/form_data.json",
                )

        assert result["escalated"] is True
        assert result["fallback_used"] is False  # Fallback was attempted but failed
        assert result["report"] == {}
        assert "error" in result
