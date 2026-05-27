"""Form filler cascade: deterministic first, Webwright fallback on escalation.

Orchestrates the form-filling pipeline step:
1. Run deterministic regex-based filler
2. Evaluate results for escalation conditions
3. If needed, run Webwright LLM-generated fallback
4. Always return structured report
"""

import json
import subprocess
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────

ESCALATION_UNKNOWN_THRESHOLD = 3

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
VENV_PYTHON = Path(__file__).parent.parent / "venv" / "bin" / "python"


# ─── Public API ──────────────────────────────────────────────────


def run_cascade(
    job_url: str,
    resume_pdf: str | None,
    form_data_path: str | None,
    no_webwright: bool = False,
) -> dict:
    """Run form filler with deterministic → Webwright fallback cascade.

    Returns dict with keys:
        - report: the JSON report from whichever path succeeded
        - escalated: bool, whether escalation was triggered
        - fallback_used: bool, whether Webwright fallback ran and succeeded
        - error: str | None, error message if both paths failed
    """
    # Run deterministic filler first
    report, exit_code = _run_deterministic(job_url, resume_pdf, form_data_path)

    # Evaluate escalation conditions
    needs_escalation = _should_escalate(report, exit_code)

    if no_webwright or not needs_escalation:
        return {
            "report": report,
            "escalated": False,
            "fallback_used": False,
            "error": None,
        }

    # Escalate to Webwright fallback
    fallback_result = _run_webwright_fallback(
        job_url=job_url,
        resume_pdf=resume_pdf,
        form_data_path=form_data_path,
        deterministic_report=report,
    )

    if fallback_result.get("success"):
        return {
            "report": fallback_result.get("report", report),
            "escalated": True,
            "fallback_used": True,
            "error": None,
        }

    # Fallback failed — return deterministic report (or empty if that crashed too)
    return {
        "report": report if report else {},
        "escalated": True,
        "fallback_used": False,
        "error": fallback_result.get("error", "Webwright fallback failed"),
    }


# ─── Internal Helpers ────────────────────────────────────────────


def _run_deterministic(
    job_url: str,
    resume_pdf: str | None,
    form_data_path: str | None,
) -> tuple[dict, int]:
    """Run the deterministic form filler via subprocess.

    Returns (report_dict, exit_code).
    """
    cmd = [str(VENV_PYTHON), str(SCRIPTS_DIR / "form_filler.py")]
    cmd += ["--url", job_url]
    if resume_pdf:
        cmd += ["--resume-pdf", resume_pdf]
    if form_data_path:
        cmd += ["--data-file", form_data_path]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return ({}, 1)
    except Exception as e:
        return ({"error": str(e)}, 1)

    if result.returncode != 0:
        return ({}, result.returncode)

    # Parse JSON report from stdout
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        report = {}

    return (report, result.returncode)


def _should_escalate(report: dict, exit_code: int) -> bool:
    """Determine if the Webwright fallback should be triggered."""
    # Deterministic crashed
    if exit_code != 0:
        return True

    # Resume upload failed
    if not report.get("resume_uploaded", True):
        return True

    # Too many unknown fields
    summary = report.get("summary", {})
    unknown_count = summary.get("total_unknown", 0)
    if unknown_count > ESCALATION_UNKNOWN_THRESHOLD:
        return True

    return False


def _run_webwright_fallback(
    job_url: str,
    resume_pdf: str | None,
    form_data_path: str | None,
    deterministic_report: dict | None = None,
) -> dict:
    """Run Webwright fallback to fill fields the deterministic filler missed.

    Returns dict with keys:
        - success: bool
        - report: dict | None, merged report if successful
        - error: str | None, error message if failed
    """
    # TODO: Implement Webwright integration in U2
    # For now, return failure so the cascade falls back gracefully
    return {
        "success": False,
        "report": None,
        "error": "Webwright fallback not yet implemented",
    }
