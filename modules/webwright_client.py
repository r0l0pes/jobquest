"""Webwright integration for ATS form filling fallback.

Generates, caches, and executes LLM-driven Playwright scripts for forms
the deterministic filler cannot handle. Wraps Microsoft's Webwright framework
with graceful degradation when Webwright is not installed.
"""

import hashlib
import json
import subprocess
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────

SCRIPT_CACHE_DIR = Path(__file__).parent.parent / "data" / "webwright_scripts"
SCRIPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

VENV_PYTHON = Path(__file__).parent.parent / "venv" / "bin" / "python"

# ─── Public API ──────────────────────────────────────────────────


def run_webwright_fallback(
    job_url: str,
    resume_pdf: str | None,
    form_data_path: str | None,
    deterministic_report: dict | None = None,
) -> dict:
    """Run Webwright fallback to fill fields the deterministic filler missed.

    Checks script cache first, then generates a new script if needed.

    Returns dict with keys:
        - success: bool
        - report: dict | None, merged report if successful
        - error: str | None, error message if failed
    """
    # Check if Webwright is available
    webwright_available = _check_webwright_available()
    if not webwright_available:
        return {
            "success": False,
            "report": None,
            "error": (
                "Webwright not installed. "
                "Install with: pip install webwright && playwright install chromium"
            ),
        }

    domain_hash = _compute_domain_hash(job_url)
    cached_script = SCRIPT_CACHE_DIR / f"{domain_hash}.py"

    # Try cached script first
    if cached_script.exists():
        return _execute_cached_script(cached_script, job_url, resume_pdf, form_data_path)

    # Generate new script via Webwright
    generation_result = _generate_script(
        job_url=job_url,
        resume_pdf=resume_pdf,
        form_data_path=form_data_path,
        deterministic_report=deterministic_report,
    )

    if not generation_result.get("success"):
        return {
            "success": False,
            "report": None,
            "error": generation_result.get("error", "Script generation failed"),
        }

    script_content = generation_result["script"]

    # Inject human-review pause before saving
    script_content = _inject_review_pause(script_content)

    # Save to cache
    cached_script.write_text(script_content)

    # Execute the generated script
    return _execute_script(cached_script, job_url, resume_pdf, form_data_path)


def clear_script_cache() -> int:
    """Remove all cached Webwright scripts. Returns count removed."""
    count = 0
    for script in SCRIPT_CACHE_DIR.glob("*.py"):
        script.unlink()
        count += 1
    return count


# ─── Internal Helpers ────────────────────────────────────────────


def _check_webwright_available() -> bool:
    """Check if Webwright is installed and importable."""
    try:
        import webwright  # noqa: F401
        return True
    except ImportError:
        return False


def _compute_domain_hash(job_url: str) -> str:
    """Compute a stable hash for the form's domain + page title prefix.

    Uses URL domain + first 50 chars of path as a simple cache key.
    """
    from urllib.parse import urlparse

    parsed = urlparse(job_url)
    domain = parsed.netloc
    path_prefix = parsed.path[:50] if parsed.path else ""
    key = f"{domain}:{path_prefix}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _generate_script(
    job_url: str,
    resume_pdf: str | None,
    form_data_path: str | None,
    deterministic_report: dict | None,
) -> dict:
    """Generate a Playwright script using Webwright's LLM-driven code generation.

    Returns dict with keys:
        - success: bool
        - script: str | None, the generated Python script
        - error: str | None
    """
    # TODO: Integrate with Webwright's programmatic API once installed.
    # For now, return a graceful failure that the cascade handles.
    return {
        "success": False,
        "script": None,
        "error": (
            "Webwright script generation not yet implemented. "
            "This is a known limitation pending Webwright dependency resolution."
        ),
    }


def _inject_review_pause(script_content: str) -> str:
    """Inject a human-review pause at the end of the script.

    Ensures the browser stays open for manual review before any submit.
    """
    pause_code = '''
# ─── Human Review Pause (injected by JobQuest) ───────────────────
print("\\n" + "=" * 50)
print("REVIEW THE FORM IN THE BROWSER")
print("1. Verify all fields are correct")
print("2. Fill any remaining fields manually")
print("3. Solve any CAPTCHA")
print("4. Submit when ready")
print("=" * 50)
try:
    input("Press Enter to close the browser...")
except EOFError:
    print("Browser will stay open. Close it manually when done.")
    page.wait_for_event("close", timeout=0)
'''

    # Append pause code before any browser.close() or final cleanup
    if "browser.close()" in script_content:
        script_content = script_content.replace(
            "browser.close()",
            f"{pause_code}\nbrowser.close()",
        )
    else:
        script_content += f"\n{pause_code}\n"

    return script_content


def _execute_cached_script(
    script_path: Path,
    job_url: str,
    resume_pdf: str | None,
    form_data_path: str | None,
) -> dict:
    """Execute a cached Playwright script."""
    return _execute_script(script_path, job_url, resume_pdf, form_data_path)


def _execute_script(
    script_path: Path,
    job_url: str,
    resume_pdf: str | None,
    form_data_path: str | None,
) -> dict:
    """Execute a Playwright script via subprocess.

    Returns dict with keys:
        - success: bool
        - report: dict | None
        - error: str | None
    """
    env = {
        "JOBQUEST_JOB_URL": job_url,
    }
    if resume_pdf:
        env["JOBQUEST_RESUME_PDF"] = resume_pdf
    if form_data_path:
        env["JOBQUEST_FORM_DATA_PATH"] = form_data_path

    try:
        result = subprocess.run(
            [str(VENV_PYTHON), str(script_path)],
            capture_output=True,
            text=True,
            timeout=300,
            env={**env, **dict()},  # merge with existing env
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "report": None,
            "error": "Script execution timed out after 5 minutes",
        }
    except Exception as e:
        return {
            "success": False,
            "report": None,
            "error": f"Script execution failed: {e}",
        }

    # Parse JSON report from stdout
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        report = {
            "raw_output": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }

    if result.returncode != 0:
        return {
            "success": False,
            "report": report,
            "error": f"Script exited with code {result.returncode}",
        }

    return {
        "success": True,
        "report": report,
        "error": None,
    }
