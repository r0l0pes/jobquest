"""Pipeline step functions for the JobQuest orchestrator.

Each step takes a context dict (ctx), enriches it, and returns it.
Steps call existing scripts via subprocess or new modules directly.
"""

import json
import os
import re
import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.markup import escape as escape_markup
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Confirm
from rich.table import Table
from rich import box

from modules import llm_telemetry, sendability
from modules.llm_client import (
    LLMClient,
    create_client,
    create_writing_client,
    create_reviewer_client,
    create_tailor_client,
    create_reviewer_client_v2,
    create_ats_client,
    create_qa_client,
    create_interview_client,
    create_fit_client_v2,
)
from modules.job_scraper import scrape_job_posting, research_company
from modules.parsers import (
    apply_grounded_ats_edits,
    apply_resume_edits,
    apply_safe_latex_replacement,
    escape_latex_text,
    extract_latex,
    fix_markdown_lists,
    locked_experience_drift,
    parse_ats_report,
    parse_qa_answers,
    parse_resume_edits,
    validate_resume_draft,
)
from scripts.render_pdf import compile_and_inspect

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
OUTPUT_DIR = PROJECT_ROOT / "output"
APPLICATIONS_FILE = PROJECT_ROOT / "data" / "applications.json"
VENV_PYTHON = str(PROJECT_ROOT / "venv" / "bin" / "python")
RESUME_CACHE_TTL = 24 * 3600  # 24 hours

def _resume_cache_file(master_resume_id: str) -> Path:
    """Cache file keyed by resume ID to avoid cross-variant cache hits."""
    safe_id = master_resume_id.replace("-", "_")[:8]
    return PROJECT_ROOT / f".master_resume_cache_{safe_id}.txt"


def _load_prompt(name: str) -> str:
    """Load a prompt template from prompts/ directory."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


# Module-level writing client cache (per task, created on first use)
_writing_client_cache: dict[str, LLMClient] = {}


def _get_writing_client() -> LLMClient:
    """DEPRECATED: Use create_tailor_client() instead.

    This shim exists for backward compatibility. It delegates to the new
    per-step factory with the same cache semantics.
    """
    import warnings
    warnings.warn(
        "_get_writing_client() is deprecated. Use create_tailor_client() "
        "for Step 3, create_qa_client() for Step 8, or "
        "create_interview_client() for Step 8b.",
        DeprecationWarning,
        stacklevel=2,
    )
    cache_key = "_singleton"
    if cache_key not in _writing_client_cache:
        _writing_client_cache[cache_key] = create_writing_client()
    return _writing_client_cache[cache_key]


# Fit-evaluation-specific client cache (separate from writing chain)
# Uses Gemini 3.1 Flash-Lite directly instead of the full writing chain.
# Rationale: fit evaluation is a simple scoring task (~500 output tokens,
# temperature 0.2). Using the full writing chain (Gemini 2.5 Pro) wastes
# a precious 25-RPD slot for a task that Flash-Lite handles equally well.
#
# If fit evaluation quality degrades (e.g., scores feel random or miss
# obvious JD-resume mismatches), revert to the writing chain by changing
# _get_fit_client to call _get_writing_client() instead.
_fit_client_cache: dict[str, LLMClient] = {}


def _get_fit_client() -> LLMClient:
    """DEPRECATED: Use create_fit_client_v2() instead.

    This shim exists for backward compatibility. It delegates to the new
    per-step factory which supports FIT_PROVIDER/FIT_MODEL env vars.
    To revert to the writing chain: call create_tailor_client() instead.
    """
    import warnings
    warnings.warn(
        "_get_fit_client() is deprecated. Use create_fit_client_v2().",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_fit_client_v2()


# Reviewer client cache (separate from writing chain and fit client)
# Uses Gemini 3 Flash → Flash-Lite fallback for adversarial quality review.
_reviewer_client_cache: dict[str, LLMClient] = {}


def _get_reviewer_client() -> LLMClient:
    """DEPRECATED: Use create_reviewer_client_v2() instead.

    This shim exists for backward compatibility. It delegates to the new
    per-step factory which supports REVIEWER_PROVIDER/REVIEWER_MODEL env vars.
    """
    import warnings
    warnings.warn(
        "_get_reviewer_client() is deprecated. Use create_reviewer_client_v2().",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_reviewer_client_v2()


def _load_behavioral_profile() -> str:
    """Load the behavioral profile from prompts/behavioral_profile.md.

    Returns empty string if the file doesn't exist — steps degrade gracefully.
    Callers should add their own section header and separator.
    """
    profile_path = PROMPTS_DIR / "behavioral_profile.md"
    if profile_path.exists():
        return profile_path.read_text()
    return ""


def _get_salary_benchmark(ctx: dict) -> dict | None:
    """Look up salary benchmarking data for the current job's company.

    Uses scripts.salary_lookup.SalaryLookup. Returns None if no data available
    or if the company isn't found — always safe to call, always graceful.
    """
    try:
        from scripts.salary_lookup import SalaryLookup
        lookup = SalaryLookup()
        company = ctx.get("job", {}).get("company", "")
        if not company:
            return None
        city = ctx.get("job", {}).get("location", "")
        return lookup.lookup(company, city)
    except Exception:
        return None


def _display_salary_benchmark(console, salary_data: dict):
    """Display salary benchmarking info in the console output."""
    categories = salary_data.get("categories", {})
    currency = salary_data.get("currency", "EUR")
    company = salary_data.get("company", "")
    city = salary_data.get("city", "")
    baseline = salary_data.get("baseline_description", "")

    table = Table(title=f"Salary Benchmark — {company}", box=box.SIMPLE)
    table.add_column("Metric", style="bold")
    table.add_column("Data Points", justify="right")
    table.add_column("Index", justify="right")
    table.add_column("Note")

    for cat_name, cat_data in categories.items():
        label = cat_name.replace("_", " ").title()
        count = cat_data.get("count", "?")
        index = cat_data.get("index", "?")
        vs_market = f"{index - 100:+.1f}% vs market" if isinstance(index, (int, float)) else ""
        table.add_row(label, str(count), str(index), vs_market)

    if city:
        location_note = f"Location: {city}"
    else:
        location_note = ""

    console.print()
    console.print(table)
    if baseline:
        console.print(f"  [dim]{baseline} ({currency})[/dim]")
    if location_note:
        console.print(f"  [dim]{location_note}[/dim]")
    console.print()


def _build_salary_qa_section(salary_data: dict) -> str:
    """Build a salary context section for Q&A generation prompt.

    Only injected when the Q&A includes a salary expectations question.
    The LLM uses this to produce informed answers.
    """
    company = salary_data.get("company", "")
    currency = salary_data.get("currency", "EUR")
    categories = salary_data.get("categories", {})
    index_label = salary_data.get("index_label", "Index")

    lines = [f"## Salary Context\n"]
    lines.append(f"{company} compensation data:")

    for cat_name, cat_data in categories.items():
        label = cat_name.replace("_", " ").title()
        count = cat_data.get("count", "?")
        index = cat_data.get("index", "?")
        vs_market = f" ({index - 100:+.1f}% vs market)" if isinstance(index, (int, float)) else ""
        lines.append(f"- {label}: index {index}{vs_market} (n={count})")

    lines.append(f"Use this data to answer salary expectation questions if the application asks.")
    lines.append(f"If no salary question is asked, ignore this section.")
    lines.append("")
    lines.append(f"---")
    lines.append("")

    return "\n".join(lines)


def _load_voice_prefix() -> str:
    """Load rodrigo-voice-lite.md as a system prompt prefix for writing steps.

    Default: lite version (~60 lines, ~500 tokens) for cost efficiency.
    Set USE_FULL_VOICE=1 in .env to use the full 322-line version when
    output quality drops and you need tighter enforcement.
    """
    voice_name = "rodrigo-voice" if os.getenv("USE_FULL_VOICE") == "1" else "rodrigo-voice-lite"
    voice_path = PROMPTS_DIR / f"{voice_name}.md"
    if voice_path.exists():
        return voice_path.read_text() + "\n\n---\n\n"
    return ""


_AI_JD_KEYWORDS = [
    "ai pm", "ai product manager", "ai-native", "ai-first", "ai tools",
    "llm", "large language model", "claude", "cursor", "copilot", "co-pilot",
    "mcp", "model context protocol", "vibe cod", "agentic", "ai agent",
    "ai workflow", "use ai", "using ai", "leverage ai", "prompt engineer",
    "generative ai", "gen ai", "genai", "ai-powered workflow",
]


def _is_ai_heavy_jd(jd_text: str) -> bool:
    """Return True if the job description has significant AI tool/workflow requirements."""
    text = jd_text.lower()
    return sum(1 for kw in _AI_JD_KEYWORDS if kw in text) >= 2


def _load_ai_pm_context() -> str:
    """Load the AI PM context doc for injection into AI-heavy JDs."""
    path = PROJECT_ROOT / "research" / "ai_pm_context.md"
    if path.exists():
        return path.read_text()
    return ""


def _run_script(script_name: str, args: list[str]) -> str:
    """Run a script from scripts/ and capture stdout."""
    cmd = [VENV_PYTHON, str(SCRIPTS_DIR / script_name)] + args
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120, cwd=str(PROJECT_ROOT)
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{script_name} failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _safe_filename(name: str) -> str:
    """Turn a company name into a filesystem-safe string."""
    return re.sub(r"[^\w\-]", "_", name).strip("_")


# Canonical application lifecycle. ``applied`` is never written by package
# generation: it requires an explicit manual action in the tracker.
APPLICATION_STATUSES = (
    "generated",
    "ready_to_apply",
    "applied",
    "screening",
    "interview",
    "offer",
    "rejected",
)
STATUS_GENERATED = "generated"
STATUS_READY_TO_APPLY = "ready_to_apply"
STATUS_APPLIED = "applied"

# Optional-stage outcomes recorded so the deterministic sendability gate never
# has to infer them from LLM prose.
STAGE_OK = "OK"
STAGE_FAILED = "FAILED"
STAGE_SKIPPED = "SKIPPED"

# Deterministic reasons recorded alongside a deliberate skip, so a stage that was
# intentionally not run is never mistaken for one that ran and failed.
STAGE_SKIP_NOT_REQUESTED = "NOT_REQUESTED"
STAGE_SKIP_NO_APPLICATION_QUESTIONS = "NO_APPLICATION_QUESTIONS"


def make_run_id(
    company_safe: str, stamp: str | None = None, suffix: str | None = None
) -> str:
    """Build a collision-safe run id, e.g. ``Acme_2026-10-05T194512_ab12cd``.

    The stamp is second-granular and the suffix is 6 hex chars of OS entropy, so
    two runs started for the same company in the same second still differ.
    """
    stamp = stamp or time.strftime("%Y-%m-%dT%H%M%S")
    suffix = suffix or os.urandom(3).hex()
    return f"{company_safe}_{stamp}_{suffix}"


def create_run_dir(
    company_safe: str, base_dir: Path | None = None, attempts: int = 25
) -> Path:
    """Create and return a brand-new unique run directory.

    Never reuses or overwrites an existing directory: the final ``mkdir`` uses
    ``exist_ok=False``, so a name collision propagates as ``FileExistsError``
    and the next candidate is tried instead.
    """
    base = Path(base_dir) if base_dir is not None else OUTPUT_DIR
    for _ in range(attempts):
        run_dir = base / make_run_id(company_safe)
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return run_dir
    raise RuntimeError(
        f"Could not allocate a unique run directory for {company_safe!r} "
        f"after {attempts} attempts under {base}"
    )


def ensure_run_dir(ctx: dict, company_safe: str) -> Path:
    """Resolve this run's output directory, creating it when it is new.

    A ``run_id`` already present in ``ctx`` is reused so a run has exactly one
    canonical identity; otherwise a fresh collision-safe directory is allocated.
    """
    existing_run_id = ctx.get("run_id")
    if existing_run_id:
        run_dir = OUTPUT_DIR / existing_run_id
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = create_run_dir(company_safe)
        ctx["run_id"] = run_dir.name
    ctx["run_dir"] = str(run_dir)
    ctx["company_safe"] = company_safe
    # Gate B.1: install the canonical run identity for LLM telemetry. This runs
    # before any pipeline step that can make an LLM call, so every emitted
    # attempt and stage result carries this run's id.
    llm_telemetry.set_run_context(ctx.get("run_id"))
    return run_dir


# ─── Step 1: Scrape Job Posting ──────────────────────────────────


def step_scrape_job(ctx: dict, llm: LLMClient, console: Console) -> dict:
    console.print("\n[bold]Step 1/9:[/bold] Scraping job posting...")

    job = scrape_job_posting(ctx["job_url"], console=console)
    ctx["job"] = job

    # Create a unique run output directory for this run.
    ensure_run_dir(ctx, _safe_filename(job.get("company") or "unknown"))

    # Merge scraped questions with user-provided ones
    scraped_qs = job.get("questions", [])
    user_qs = ctx.get("questions", [])
    all_qs = list(dict.fromkeys(scraped_qs + user_qs))  # dedupe, keep order
    ctx["all_questions"] = all_qs

    # Enrich with structured fields (salary, skills, remote policy, etc.)
    try:
        from modules.scrapers.sources.structured_extractor import StructuredExtractor
        extractor = StructuredExtractor()
        job = extractor.enrich(job)
        ctx["job"] = job
        skills = job.get("required_skills", [])
        nice_skills = job.get("nice_to_have_skills", [])
        if skills or nice_skills:
            console.print(
                f"  [dim]Structured extraction: {len(skills)} required skills, "
                f"{len(nice_skills)} nice-to-have[/dim]"
            )
    except Exception:
        pass  # Graceful degradation — never block the pipeline

    console.print(
        f"  Job: [bold]{job.get('title', '?')}[/bold] "
        f"at [bold]{job.get('company', '?')}[/bold]"
    )
    console.print(
        f"  Source: {job.get('source', '?')} | "
        f"Description: {len(job.get('description', ''))} chars"
    )
    if all_qs:
        console.print(f"  Application questions found: {len(all_qs)}")

    return ctx


# ─── Step 2: Read Master Resume ──────────────────────────────────


def step_read_master_resume(
    ctx: dict, llm: LLMClient, console: Console
) -> dict:
    console.print("\n[bold]Step 2/9:[/bold] Reading master resume from Notion...")

    from config import MASTER_RESUME_ID
    cache_file = _resume_cache_file(MASTER_RESUME_ID)

    # Use local cache if fresh (avoids Notion API slowness on every run)
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < RESUME_CACHE_TTL:
            output = cache_file.read_text()
            if len(output) < 500:
                console.print(f"  [yellow]Cache corrupted ({len(output)} chars), re-fetching...[/yellow]")
                cache_file.unlink()
            else:
                console.print(f"  Loaded {len(output)} chars (cached {int(age / 3600)}h ago)")
                ctx["master_resume"] = output
                return ctx

    output = _run_script(
        "notion_reader.py", ["page", MASTER_RESUME_ID, "--text"]
    )
    if len(output) < 500:
        raise RuntimeError(
            f"Master resume read returned suspiciously short content "
            f"({len(output)} chars). Notion may be degraded. Raw: {output[:200]!r}"
        )
    cache_file.write_text(output)
    ctx["master_resume"] = output
    console.print(f"  Loaded {len(output)} chars")
    return ctx



def _slim_resume_for_analysis(master_resume: str) -> str:
    """Return a condensed version of the master resume for step 3a (analysis only).

    The tailoring brief only needs to know which roles exist and what bullets
    are available to target. Sending the full resume here wastes ~3,000 tokens
    per application. This function keeps role headers and first line of each
    bullet, stripping verbose detail.

    Step 3b still receives the full master resume for accurate LaTeX generation.
    """
    lines = master_resume.split("\n")
    slim = []
    bullet_count = 0
    for line in lines:
        stripped = line.strip()
        # Always keep headers, role titles, date lines, section markers
        if not stripped:
            slim.append("")
            bullet_count = 0
            continue
        if stripped.startswith(("#", "##", "**", "---", "=")) or "|" in stripped:
            slim.append(line)
            bullet_count = 0
            continue
        # Keep first 2 bullets per block, skip the rest
        if stripped.startswith("-") or stripped.startswith("•"):
            if bullet_count < 2:
                # Truncate long bullets to 120 chars
                truncated = stripped[:120] + ("…" if len(stripped) > 120 else "")
                slim.append("  " + truncated)
                bullet_count += 1
            # else: skip
            continue
        slim.append(line)
    return "\n".join(slim)


# ─── Fit Evaluation Gate Exception ─────────────────────────────


class FitGateBlocked(Exception):
    """Raised when the fit evaluation gate blocks the pipeline.
    
    This is not a program error — it means the job is a poor fit and
    the user (or auto-apply logic) chose not to proceed.
    """
    pass


# ─── Fit Evaluation (Step 2b) ───────────────────────────────────


def _load_career_config() -> dict:
    """Load career goals, deal-breakers, and constraints from career_config.json.
    
    Returns empty dict if the file is missing or malformed.
    """
    config_path = PROJECT_ROOT / "data" / "career_config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _career_config_evidence() -> str | None:
    """Career config rendered as candidate-controlled evidence text."""
    try:
        config = _load_career_config()
    except (OSError, UnicodeError, ValueError, TypeError):
        # Evidence loading must never void the verdict.
        return None
    return json.dumps(config) if config else None


def _load_story_bank_evidence() -> str | None:
    """Candidate-authored story bank, used only as grounding evidence."""
    path = PROJECT_ROOT / "interview-prep" / "story-bank.md"
    try:
        text = path.read_text()
    except (OSError, UnicodeError, ValueError, TypeError):
        # Never fatal here: a missing/unreadable story bank only thins the corpus.
        return None
    return text or None


def _jd_skill_terms(ctx: dict) -> tuple[str, ...]:
    """Skill terms the pipeline extracted from the posting.

    The job description states what the employer wants; it is never proof that
    the candidate did the work. These are therefore handed to the sendability
    gate as terms that must be grounded in candidate evidence, which is what
    closes the circular-certification hole seen in the Clickboat pilot.
    """
    job = ctx.get("job") or {}
    terms: list[str] = []
    for key in ("required_skills", "nice_to_have_skills"):
        for value in job.get(key) or []:
            if isinstance(value, str) and value.strip():
                terms.append(value.strip())
    return tuple(dict.fromkeys(terms))


def _compute_fit_score(dimensions: dict) -> dict:
    """Compute weighted fit score from dimension scores.
    
    Args:
        dimensions: Dictionary with keys technical_skills, experience_match,
                    behavioral_fit, career_alignment, location.
    
    Returns:
        {"score": int, "label": str, "location_pass": bool}
    """
    weights = {
        "technical_skills": 0.30,
        "experience_match": 0.25,
        "behavioral_fit": 0.15,
        "career_alignment": 0.30,
    }

    # Location is pass/fail
    location = dimensions.get("location", {})
    location_pass = location.get("status", "").upper() == "PASS"

    if not location_pass:
        return {"score": 0, "label": "POOR FIT (Location Failed)", "location_pass": False}

    total = 0.0
    for dim, weight in weights.items():
        dim_data = dimensions.get(dim, {})
        score = dim_data.get("score", 50) if isinstance(dim_data, dict) else dim_data
        total += score * weight

    score = round(total)

    if score >= 75:
        label = "STRONG FIT"
    elif score >= 60:
        label = "GOOD FIT"
    elif score >= 45:
        label = "MODERATE"
    elif score >= 30:
        label = "WEAK"
    else:
        label = "POOR FIT"

    return {"score": score, "label": label, "location_pass": True}


def _parse_fit_evaluation(raw_response: str) -> dict | None:
    """Parse the JSON fit evaluation from LLM output.
    
    Expects JSON between ```json and ``` markers.
    Returns None if parsing fails.
    """
    import re as _re
    match = _re.search(r"```json\s*\n(.*?)\n```", raw_response, _re.DOTALL)
    if not match:
        # Try without code fences
        match = _re.search(r'\{[^}]*"dimensions"', raw_response)
        if match:
            # Try to parse the whole block
            try:
                return json.loads(raw_response)
            except json.JSONDecodeError:
                return None
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def step_evaluate_fit(
    ctx: dict, llm: LLMClient, console: Console,
    auto_apply: bool = False
) -> dict:
    """Evaluate job fit before tailoring.
    
    Calls LLM to score fit across 5 dimensions, computes weighted score,
    and gates the pipeline based on score thresholds.
    
    Raises FitGateBlocked if the job is a poor fit and the pipeline should stop.
    """
    console.print("\n[bold]Step 2b:[/bold] Evaluating job fit...")

    # Load career config
    career_config = _load_career_config()
    career_text = json.dumps(career_config, indent=2) if career_config else "No career config available."

    # Load behavioral profile (optional — graceful empty fallback)
    behavioral_profile = _load_behavioral_profile()

    # Load fit evaluation prompt
    fit_prompt = _load_prompt("fit_evaluation")

    # Use lightweight Gemini Flash-Lite for scoring — fit evaluation is a
    # short classification task (~500 output tokens, temperature 0.2).
    # The full writing chain (Gemini 2.5 Pro) is overkill here and would
    # waste one of the 25 daily Pro requests.
    # If fit quality degrades: switch to _get_writing_client().
    fit_llm = create_fit_client_v2()

    with llm_telemetry.stage_context("fit", step_index=3) as st:
        try:
            raw = fit_llm.generate(
                fit_prompt,
                f"## Job Posting\n\n"
                f"**Title:** {ctx['job']['title']}\n"
                f"**Company:** {ctx['job']['company']}\n\n"
                f"{ctx['job']['description'][:4000]}\n\n"
                f"---\n\n"
                f"## Master Resume\n\n{ctx['master_resume'][:4000]}\n\n"
                f"---\n\n"
                f"## Career Config\n\n{career_text}\n\n"
                f"---\n\n"
                + (f"## Behavioral Profile\n\n{behavioral_profile}\n\n---\n\n" if behavioral_profile else "")
                + f"Evaluate the fit and return the JSON result.",
                temperature=0.2,
            )
        except Exception as e:
            # LLM telemetry only: the existing degradation path is unchanged.
            st.set_success(False)
            st.set_degradation("optional_stage_failed")
            console.print(f"  [yellow]Fit evaluation LLM call failed ({e}). Proceeding without gate.[/yellow]")
            ctx["fit_evaluation"] = None
            ctx["fit_score"] = 50
            ctx["fit_label"] = "UNKNOWN (eval failed)"
            return ctx

        # Parse the response
        evaluation = _parse_fit_evaluation(raw)
        st.set_parse_result(evaluation is not None)
        if evaluation is None:
            st.set_success(False)
            st.set_degradation("optional_stage_failed")
            console.print("  [yellow]Failed to parse fit evaluation JSON. Proceeding without gate.[/yellow]")
            ctx["fit_evaluation"] = None
            ctx["fit_score"] = 50
            ctx["fit_label"] = "UNKNOWN (parse failed)"
            return ctx

    ctx["fit_evaluation"] = evaluation

    # Compute score
    dimensions = evaluation.get("dimensions", {})
    result = _compute_fit_score(dimensions)
    score = result["score"]
    label = result["label"]

    ctx["fit_score"] = score
    ctx["fit_label"] = label

    # Save to run dir
    run_dir = Path(ctx["run_dir"])
    (run_dir / f"fit_evaluation_{ctx['company_safe']}.md").write_text(raw)
    (run_dir / f"fit_evaluation_{ctx['company_safe']}.json").write_text(json.dumps(evaluation, indent=2))

    # Display evaluation
    _display_fit_evaluation(console, evaluation, score, label)

    # Salary benchmarking (optional — silent skip if no data)
    salary_data = _get_salary_benchmark(ctx)
    if salary_data:
        ctx["salary_benchmark"] = salary_data
        _display_salary_benchmark(console, salary_data)

    # Gate logic
    style = "green" if score >= 75 else "yellow" if score >= 45 else "red"
    console.print(f"  Fit Score: [{style}]{score}/100 — {label}[/{style}]")

    # Always block on location fail
    if not result["location_pass"]:
        console.print("\n  [red]✗ Location constraint not met. Pipeline stopped.[/red]")
        if not auto_apply:
            raise FitGateBlocked(
                f"Location FAIL for {ctx['job']['company']} — "
                f"{ctx['job']['title']}"
            )
        else:
            console.print("  [yellow]Auto-apply enabled, but location FAIL overrides. Stopping.[/yellow]")
            raise FitGateBlocked(
                f"Location FAIL for {ctx['job']['company']} — "
                f"{ctx['job']['title']} (auto-apply cannot override location fail)"
            )

    # Auto-apply skips the gate for all other scores
    if auto_apply:
        console.print(f"  [dim]Auto-apply enabled — proceeding regardless of fit score.[/dim]")
        return ctx

    # Strong fit: proceed automatically
    if score >= 75:
        console.print("  [green]✓ STRONG FIT — proceeding automatically.[/green]")
        return ctx

    # Good fit: proceed, note gaps
    if score >= 60:
        console.print("  [green]✓ GOOD FIT — proceeding. Review gaps above.[/green]")
        return ctx

    # Moderate: warn, ask user
    if score >= 45:
        console.print("\n  [yellow]⚠ MODERATE fit — this may not be the best use of your time.[/yellow]")
        import sys
        if sys.stdin.isatty():
            proceed = Confirm.ask("  Proceed with tailoring?", default=True)
            if not proceed:
                console.print("  [red]✗ User declined. Pipeline stopped.[/red]")
                raise FitGateBlocked(
                    f"User declined moderate fit ({score}/100) for {ctx['job']['company']}"
                )
            return ctx
        else:
            console.print("  [yellow]Non-interactive mode — proceeding with caution.[/yellow]")
            return ctx

    # Weak: strong warning, ask user
    if score >= 30:
        console.print("\n  [red]⚠ WEAK fit — this role is likely a poor match.[/red]")
        import sys
        if sys.stdin.isatty():
            proceed = Confirm.ask("  Proceed anyway?", default=False)
            if not proceed:
                console.print("  [red]✗ User declined. Pipeline stopped.[/red]")
                raise FitGateBlocked(
                    f"User declined weak fit ({score}/100) for {ctx['job']['company']}"
                )
            console.print("  [yellow]Proceeding by user override.[/yellow]")
            return ctx
        else:
            console.print("  [red]Non-interactive mode — stopping for weak fit.[/red]")
            raise FitGateBlocked(
                f"Auto-stopped weak fit ({score}/100) for {ctx['job']['company']}"
            )

    # Poor fit: stop
    console.print("\n  [red]✗ POOR FIT — pipeline stopped. This role is not worth your time.[/red]")
    raise FitGateBlocked(
        f"Poor fit ({score}/100) for {ctx['job']['company']} — {ctx['job']['title']}"
    )


def _display_fit_evaluation(console: Console, evaluation: dict, score: int, label: str):
    """Render the fit evaluation as a formatted table and markdown sections."""
    dims = evaluation.get("dimensions", {})

    # Dimension table
    table = Table(title=f"Job Fit Evaluation: {label}", box=box.SIMPLE)
    table.add_column("Dimension", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Notes")

    for dim_key, dim_label in [
        ("technical_skills", "Technical Skills"),
        ("experience_match", "Experience Match"),
        ("behavioral_fit", "Behavioral Fit"),
        ("career_alignment", "Career Alignment"),
    ]:
        dim = dims.get(dim_key, {})
        s = dim.get("score", "?")
        note = (dim.get("note", "") or "")[:100]
        style = "green" if isinstance(s, (int, float)) and s >= 70 else "yellow" if isinstance(s, (int, float)) and s >= 50 else "red"
        table.add_row(dim_label, f"[{style}]{s}/100[/{style}]", note)

    # Location row
    loc = dims.get("location", {})
    loc_status = loc.get("status", "?")
    loc_note = (loc.get("note", "") or "")[:100]
    loc_style = "green" if loc_status.upper() == "PASS" else "red"
    table.add_row("Location", f"[{loc_style}]{loc_status}[/{loc_style}]", loc_note)

    console.print()
    console.print(table)

    # Overall score
    style = "green" if score >= 75 else "yellow" if score >= 45 else "red"
    console.print(f"\n  [bold]Overall Score: [{style}]{score}/100 — {label}[/{style}]")

    # Strengths
    strengths = evaluation.get("strengths", [])
    if strengths:
        console.print("\n  [bold]Key Strengths:[/bold]")
        for s in strengths:
            console.print(f"    • {s}")

    # Gaps
    gaps = evaluation.get("gaps", [])
    if gaps:
        console.print("\n  [bold]Gaps to Address:[/bold]")
        for g in gaps:
            console.print(f"    • {g}")

    # Recommendation
    rec = evaluation.get("recommendation", "")
    if rec:
        console.print(f"\n  [bold]Recommendation:[/bold] {rec}")


# ─── Step 3: Tailor Resume via LLM ───────────────────────────────


TAGLINES = {
    "growth_pm": "Experiments that accelerate revenue.",
    "generalist": "End-to-end ownership. Outcomes delivered.",
    "ai_pm": "AI products shipped. Prototypes to production.",
}


def step_tailor_resume(ctx: dict, llm: LLMClient, console: Console) -> dict:
    writing_llm = create_tailor_client()
    console.print("\n[bold]Step 3/9:[/bold] Tailoring resume...")

    from config import ROLE_VARIANT
    tagline = TAGLINES.get(ROLE_VARIANT, TAGLINES["growth_pm"])

    # --- Stage 3a: JD analysis (free-tier LLM) ---
    # Produces a structured tailoring brief before the writing model touches anything.
    # This separates "figuring out what to do" from "doing it", which produces
    # more deliberate keyword placement and a better-reasoned summary strategy.
    console.print(f"  3a: Analyzing job requirements...")
    analysis_system = _load_prompt("jd_analysis")

    ai_context_section = ""
    ai_pm_variant = (ROLE_VARIANT == "ai_pm")
    if ai_pm_variant or _is_ai_heavy_jd(ctx['job']['description']):
        if ai_pm_variant:
            console.print("  [dim]AI-PM variant: tagging as AI-heavy[/dim]")
        ai_context_section = (
            f"## Role Context\n\n"
            f"This is an AI-heavy role. The candidate's Postscript AI work "
            f"(message optimization engine, SMS personalization) is the primary story. "
            f"Foreground this experience over HELLA/Accenture/C&A.\n\n"
            f"---\n\n"
        )
    else:
        console.print("  [dim]Non-AI role: no contextual emphasis[/dim]")
        ai_context_section = ""

    analysis_user = (
        f"## Job Posting\n\n"
        f"**Title:** {ctx['job']['title']}\n"
        f"**Company:** {ctx['job']['company']}\n\n"
        f"{ctx['job']['description']}\n\n"
        f"---\n\n"
        f"## Candidate Resume (structure summary — step 3b has the full text)\n\n"
        f"{_slim_resume_for_analysis(ctx['master_resume'])}\n\n"
        f"---\n\n"
        f"{ai_context_section}"
        f"Produce the tailoring brief."
    )
    # Gate B.1: free-form prose stage, so there is no structured parse outcome
    # to report (structured_parse_success stays null for this stage).
    with llm_telemetry.stage_context("tailor_3a", step_index=4):
        tailoring_brief = writing_llm.generate(analysis_system, analysis_user, temperature=0.2)
    ctx["tailoring_brief"] = tailoring_brief

    # Save brief to run dir for debugging
    run_dir = Path(ctx["run_dir"])
    (run_dir / f"tailoring_brief_{ctx['company_safe']}.md").write_text(tailoring_brief)
    console.print(f"  Tailoring brief: {len(tailoring_brief)} chars")

    # --- Stage 3b: LaTeX generation (writing LLM) ---
    # Two modes:
    # - Targeted edit mode (TARGETED_EDITS=1): model returns a small JSON patch
    #   (~400-600 tokens output). Applied to the base template. Works with Flash.
    # - Full generation (default): model writes complete LaTeX (~4,000+ tokens).
    #   Required for DeepSeek, Gemini Pro, OpenRouter.
    console.print(f"  3b: Generating LaTeX ({writing_llm.model_name()})...")

    targeted_mode = os.getenv("TARGETED_EDITS", "1") != "0"
    # Set when the targeted path technically succeeds but its accepted artifact is
    # effectively identical to this run's baseline, i.e. nothing was tailored.
    no_effective_edits = False

    if targeted_mode:
        base_latex = (PROJECT_ROOT / "templates" / "resume.tex").read_text()
        edits_system = _load_voice_prefix() + _load_prompt("resume_edits")
        edits_user = (
            f"## Tailoring Brief\n\n{tailoring_brief}\n\n"
            f"---\n\n"
            f"## Master Resume\n\n{ctx['master_resume']}\n\n"
            f"---\n\n"
            f"Return only the JSON with the targeted changes."
        )
        with llm_telemetry.stage_context("tailor_3b_edits", step_index=4) as st:
            raw_edits = writing_llm.generate(edits_system, edits_user, temperature=0.2)
            ctx["tailor_raw"] = raw_edits
            edits = parse_resume_edits(raw_edits)
            st.set_parse_result(edits is not None)
            if not edits:
                # Gate B.1 telemetry only: the existing code below falls through
                # to full generation, which is recorded as a degradation here.
                st.set_success(False)
                st.set_degradation("targeted_parse_failed_full_generation_used")
        if edits:
            tagline_str = tagline
            edits["tagline"] = edits.get("tagline") or tagline_str
            patched = apply_resume_edits(base_latex, edits, ctx["master_resume"])
            # Inject the correct tagline from pipeline config (overrides model output)
            _tagline_repl = "{\\small " + tagline + "}"
            patched = re.sub(
                r"\{\\small [^}]+\}",
                lambda m: _tagline_repl,
                patched, count=1,
            )
            ctx["tailored_latex"] = fix_markdown_lists(patched)
            # Effective-tailoring check. The reference puts the untouched baseline
            # through the very same deterministic, non-tailoring transformations,
            # so a config-driven change (such as the forced tagline) is never
            # counted as tailoring. The comparison itself ignores only
            # serialization churn (line endings, trailing spaces, blank lines), so
            # a patch that reproduces the baseline content with different
            # formatting still counts as having no effective edit. The reference
            # is kept on ctx so sendability can re-judge the FINAL artifact
            # against the very same run baseline.
            no_effect_reference = fix_markdown_lists(
                re.sub(
                    r"\{\\small [^}]+\}",
                    lambda m: _tagline_repl,
                    base_latex,
                    count=1,
                )
            )
            ctx["tailoring_noop_reference"] = no_effect_reference
            no_effective_edits = (
                sendability.normalize_for_tailoring_effect_comparison(
                    ctx["tailored_latex"]
                )
                == sendability.normalize_for_tailoring_effect_comparison(
                    no_effect_reference
                )
            )
            console.print(f"  Targeted edits applied: {len(edits.get('postscript_bullets', []))} Postscript bullets, skills updated")
        else:
            console.print("  [yellow]Targeted edits parse failed, falling back to full generation[/yellow]")
            targeted_mode = False  # fall through to full generation below

    if not targeted_mode:
        system_prompt = _load_voice_prefix() + _load_prompt("resume_tailor")
        user_prompt = (
            f"## Tailoring Brief\n\n"
            f"This analysis was produced for you in advance. Follow it — it tells you "
            f"which bullets to touch, what the summary strategy is, and what to leave alone.\n\n"
            f"{tailoring_brief}\n\n"
            f"---\n\n"
            f"## Locked Header (copy character-for-character, do not change anything)\n\n"
            f"\\hypersetup{{colorlinks=true, linkcolor=black, urlcolor=black, citecolor=black}}\n"
            f"\\begin{{center}}\n"
            f"  {{\\Huge\\bfseries Rodrigo Lopes,}} {{\\small {tagline}}}\\\\[6pt]\n"
            f"  \\href{{https://rodrigolopes.xyz/?utm_source=resume&utm_medium=pdf}}{{rodrigolopes.xyz}} \\textbar{{}}\n"
            f"  \\href{{mailto:contact@rodrigolopes.xyz}}{{contact@rodrigolopes.xyz}} \\textbar{{}}\n"
            f"  12435, Berlin\n"
            f"\\end{{center}}\n\n"
            f"---\n\n"
            f"## Master Resume\n\n"
            f"{ctx['master_resume']}\n\n"
            f"---\n\n"
            f"## Job Posting\n\n"
            f"**URL:** {ctx['job']['url']}\n"
            f"**Title:** {ctx['job']['title']}\n"
            f"**Company:** {ctx['job']['company']}\n\n"
            f"{ctx['job']['description']}\n\n"
            f"---\n\n"
            f"Generate the complete tailored LaTeX resume following the tailoring brief above.\n\n"
            f"CRITICAL: The output MUST include every single section of the master resume — "
            f"all experience roles, Skills & Tools, Certifications, Languages, and Education. "
            f"Sections marked 'do not change' or 'leave as-is' in the brief must be copied "
            f"VERBATIM from the master resume. 'Leave as-is' means reproduce it exactly, NOT omit it. "
            f"A resume missing any section is broken and unusable.\n\n"
            f"Output ONLY the LaTeX content between ```latex and ``` markers."
        )

        # Completeness validator: checks that the extracted LaTeX has all required
        # sections. If not, _WritingFallbackClient falls back to the next provider.
        _REQUIRED_SECTIONS = [
            (r"\\section\*\{Experience\}", "Experience"),
            (r"\\section\*\{Skills", "Skills & Tools"),
            (r"\\section\*\{Education\}", "Education"),
        ]

        def _is_complete_latex(raw_response: str) -> bool:
            """Return True if the raw LLM response contains a complete LaTeX resume."""
            latex = extract_latex(raw_response)
            if not latex:
                return False
            missing = [
                name for pattern, name in _REQUIRED_SECTIONS
                if not re.search(pattern, latex)
            ]
            if missing:
                (run_dir / f"TRUNCATED_resume_{ctx['company_safe']}.tex").write_text(latex)
                console.print(f"  [yellow]Truncated output (missing: {', '.join(missing)}), trying next writing provider...[/yellow]")
                return False
            return True

        with llm_telemetry.stage_context("tailor_3b_full", step_index=4) as st:
            raw = writing_llm.generate(
                system_prompt, user_prompt, temperature=0.3,
                content_validator=_is_complete_latex
            )
            ctx["tailor_raw"] = raw

            latex = extract_latex(raw)
            st.set_parse_result(latex is not None)
            if not latex:
                raise RuntimeError(
                    "LLM did not return parseable LaTeX. "
                    "Raw response saved to run directory for debugging."
                )

        ctx["tailored_latex"] = fix_markdown_lists(latex)
        console.print(f"  Tailored LaTeX generated: {len(latex)} chars")

    # Record the mode actually used. This is the single source of truth for
    # downstream checks that only apply to template-derived targeted edits; the
    # configured TARGETED_EDITS value is only intent and may differ from what ran.
    ctx["tailoring_mode"] = (
        sendability.TAILORING_TARGETED if targeted_mode else sendability.TAILORING_FULL
    )

    integrity_errors = validate_resume_draft(ctx["tailored_latex"], ctx["master_resume"])
    if integrity_errors:
        console.print(
            f"  [yellow]Factual-integrity validator rejected Stage 3b draft: "
            f"{'; '.join(integrity_errors[:4])}[/yellow]"
        )
        ctx["tailored_latex"] = (PROJECT_ROOT / "templates" / "resume.tex").read_text()
        # The requested tailored resume did not survive validation and the
        # untailored base template was substituted. Record that outcome here -
        # the only place that knows it - rather than inferring it downstream.
        ctx["tailoring_outcome"] = sendability.TAILORING_OUTCOME_FALLBACK_UNTAILORED
    elif no_effective_edits:
        # The patch applied and validated, but the accepted resume is byte-identical
        # to this run's baseline, so no tailoring actually happened.
        ctx["tailoring_outcome"] = (
            sendability.TAILORING_OUTCOME_NO_EFFECTIVE_EDITS
        )
    else:
        ctx["tailoring_outcome"] = sendability.TAILORING_OUTCOME_TAILORED

    # --- Stage 3c: Brief compliance review (free-tier LLM) ---
    # Checks whether the writing model followed the plan. Runs automatically
    # on every tailor, logs issues to the run dir, never blocks the pipeline.
    console.print("  3c: Checking brief compliance...")
    review_system = _load_prompt("tailor_review")
    review_user = (
        f"## Tailoring Brief\n\n{tailoring_brief}\n\n"
        f"---\n\n"
        f"## Generated LaTeX\n\n{ctx['tailored_latex']}\n\n"
        f"---\n\n"
        f"Review for compliance with the brief."
    )
    # Gate B.1: free-form prose stage (no structured parse outcome).
    with llm_telemetry.stage_context("tailor_3c", step_index=4) as st:
        try:
            review_raw = writing_llm.generate(
                review_system, review_user, temperature=0.1
            )
            ctx["tailor_review"] = review_raw
            (run_dir / f"tailor_review_{ctx['company_safe']}.md").write_text(review_raw)

            if review_raw.strip().upper().startswith("PASS"):
                console.print("  [green]Brief compliance: PASS[/green]")
            else:
                high_count = review_raw.upper().count("SEVERITY: HIGH")
                if high_count > 0:
                    console.print(
                        f"  [yellow]Brief compliance: {high_count} HIGH issue(s) "
                        f"— see tailor_review_{ctx['company_safe']}.md[/yellow]"
                    )
                else:
                    console.print("  [dim]Brief compliance: minor divergences logged.[/dim]")
        except Exception as err:
            st.set_success(False)
            st.set_degradation("optional_stage_failed")
            console.print(f"  [dim]Brief compliance check skipped: {err}[/dim]")

    return ctx


# ─── Step 4: Write .tex File ─────────────────────────────────────


def step_write_tex(ctx: dict, llm: LLMClient, console: Console) -> dict:
    console.print("\n[bold]Step 4/9:[/bold] Writing .tex file...")

    run_dir = Path(ctx["run_dir"])
    filename = f"Resume_Rodrigo-Lopes.tex"
    tex_path = run_dir / filename

    tex_path.write_text(ctx["tailored_latex"])
    ctx["tex_path"] = str(tex_path)

    console.print(f"  Written: {tex_path}")
    return ctx


# ─── Reviewer Steps: adversarial draft critique + revision ───────


def step_review_drafts(ctx: dict, llm: LLMClient, console: Console) -> dict:
    """Review the tailored LaTeX draft with a separate adversarial LLM.

    Runs after step_write_tex, before step_ats_check. Uses a different model
    (Gemini 3 Flash) to catch issues the drafter missed: fabricated content,
    missed keywords, tone mismatches, company-specific angles, repetition.
    """
    if ctx.get("skip_reviewer"):
        console.print("\n[bold]Reviewer:[/bold] [yellow]Skipped (--skip-reviewer)[/yellow]")
        ctx["review_feedback"] = None
        ctx["reviewer_status"] = STAGE_SKIPPED
        return ctx

    console.print("\n[bold]Step 5/10:[/bold] Reviewing drafts (adversarial review)...")

    reviewer = create_reviewer_client_v2()
    console.print(f"  Reviewer model: {reviewer.model_name()}")

    # Build review prompt with full context
    review_system = _load_prompt("reviewer")
    job_text = ctx["job"].get("description", "") or ""
    company = ctx["job"].get("company", "Unknown")
    title = ctx["job"].get("title", "Unknown")
    brief = ctx.get("tailoring_brief", "")
    draft = ctx.get("tailored_latex", "")
    master = ctx["master_resume"]
    behavioral_profile = _load_behavioral_profile()

    review_user = (
        f"## Job Posting\n\n"
        f"**Title:** {title}\n**Company:** {company}\n\n"
        f"{job_text}\n\n"
        f"---\n\n"
        f"## Tailoring Brief (what the drafter was told to do)\n\n"
        f"{brief}\n\n"
        f"---\n\n"
        f"## Draft LaTeX Resume (what the drafter produced)\n\n"
        f"```latex\n{draft}\n```\n\n"
        f"---\n\n"
        f"## Candidate Master Resume (ground truth)\n\n"
        f"{master}\n\n"
        f"---\n\n"
        + (f"## Behavioral Profile\n\n{behavioral_profile}\n\n---\n\n" if behavioral_profile else "")
        + f"Review the draft against the tailoring brief, job description, "
        f"and master resume. Produce Part A (JSON edits) and Part B (narrative "
        f"suggestions) following the reviewer prompt format."
    )

    with llm_telemetry.stage_context("reviewer", step_index=6) as st:
        try:
            review_raw = reviewer.generate(review_system, review_user, temperature=0.2)
            feedback = _parse_review_feedback(review_raw, console)
            ctx["review_feedback"] = feedback
            st.set_parse_result(bool(feedback.get("structure_recognized")))
            # Parsing never raises. Success means a valid reviewer response was
            # recognised, not that the reviewer found something to criticise: an
            # empty Part A with a well-formed Part B is a legitimate clean review.
            if feedback.get("structure_recognized"):
                ctx["reviewer_status"] = STAGE_OK
            else:
                st.set_success(False)
                st.set_degradation("optional_stage_failed")
                console.print(
                    "  [yellow]Reviewer response was not recognisable as a "
                    "review.[/yellow]"
                )
                ctx["reviewer_status"] = STAGE_FAILED

            # Save to run dir for debugging
            run_dir = Path(ctx["run_dir"])
            (run_dir / f"review_feedback_{ctx['company_safe']}.md").write_text(
                review_raw
            )

        except Exception as err:
            st.set_success(False)
            st.set_degradation("optional_stage_failed")
            console.print(f"  [yellow]Reviewer call failed ({err}) — continuing without review.[/yellow]")
            ctx["review_feedback"] = None
            ctx["reviewer_status"] = STAGE_FAILED

    return ctx


def step_apply_review(ctx: dict, llm: LLMClient, console: Console) -> dict:
    """Apply the reviewer's feedback to the LaTeX draft.

    Applies Part A JSON edits via exact string replacement. Logs Part B
    narrative suggestions. Silently skips edits whose old_string can't be
    found. Skipped entirely if reviewer was disabled or returned no feedback.
    """
    feedback = ctx.get("review_feedback")
    if feedback is None:
        return ctx  # Reviewer was skipped or failed

    console.print("\n[bold]Step 5b/10:[/bold] Applying reviewer feedback...")

    edits = feedback.get("part_a", [])
    suggestions = feedback.get("part_b", [])

    # In targeted-edit mode the canonical FORVIA / Accenture / C&A experience
    # blocks are locked to the factual template and must not drift.
    targeted_mode = os.getenv("TARGETED_EDITS", "1") != "0"

    applied = 0
    skipped = 0
    latex = ctx.get("tailored_latex", "")

    for edit in edits:
        old = edit.get("old_string", "")
        new = edit.get("new_string", "")
        reason = edit.get("reason", "?")

        if not old:
            skipped += 1
            continue

        if old in latex:
            candidate = apply_safe_latex_replacement(latex, old, new)
            integrity_errors = validate_resume_draft(candidate, ctx["master_resume"])
            drift = locked_experience_drift(latex, candidate) if targeted_mode else []
            if integrity_errors:
                skipped += 1
                console.print(
                    f"  [yellow]⊙[/yellow] factual-integrity edit rejected (skipped): "
                    f"{reason}"
                )
            elif drift:
                skipped += 1
                console.print(
                    f"  [yellow]⊙[/yellow] locked experience edit rejected "
                    f"({', '.join(drift)}): {reason}"
                )
            else:
                latex = candidate
                applied += 1
                console.print(f"  [green]✓[/green] {reason}")
        else:
            skipped += 1
            console.print(f"  [yellow]⊙[/yellow] old_string not found (skipped): {reason}")

    ctx["tailored_latex"] = latex
    if ctx.get("tex_path"):
        Path(ctx["tex_path"]).write_text(latex)

    # Log narrative suggestions
    if suggestions:
        run_dir = Path(ctx["run_dir"])
        sug_path = run_dir / f"review_suggestions_{ctx['company_safe']}.md"
        sug_text = "\n".join(
            f"### Suggestion {i + 1}\n{s}"
            for i, s in enumerate(suggestions)
        )
        sug_path.write_text(sug_text)
        console.print(f"  [dim]{len(suggestions)} narrative suggestion(s) saved to {sug_path.name}[/dim]")

    console.print(f"  Reviewer: {applied} edit(s) applied, {skipped} skipped")
    return ctx


def _parse_review_feedback(raw: str, console: Console) -> dict:
    """Parse reviewer output into Part A (JSON edits) and Part B (narrative).

    Also reports whether the reply was recognisably a reviewer response. A
    review that legitimately proposes no edits and no suggestions is still a
    successful review; only a reply we cannot recognise is a failure.
    """
    import json

    part_a: list[dict] = []
    part_b: list[str] = []
    structure_recognized = False

    # Extract Part A: JSON block
    json_match = re.search(r"```(?:json)?\s*\n?(\[[\s\S]*?\])\s*\n?```", raw)
    if json_match:
        try:
            part_a = json.loads(json_match.group(1))
            if isinstance(part_a, list):
                # A parsed fenced array is a recognisable reviewer response even
                # when empty: "no mechanical edits" is a valid review outcome.
                structure_recognized = True
            else:
                part_a = []
        except json.JSONDecodeError:
            console.print("  [yellow]Failed to parse Part A JSON — no edits applied.[/yellow]")
            part_a = []

    # Extract Part B: lines starting with SUGGESTION:
    in_part_b = False
    current_suggestion: list[str] = []
    for line in raw.split("\n"):
        stripped = line.strip()
        # Accept any heading level or decoration. prompts/reviewer.md mandates
        # ``### Part A - Structured JSON Edits`` / ``### Part B - ...``, but the
        # model may emit any heading depth, so match on the Part keyword alone.
        heading = stripped.lstrip("#*-— ").strip().lower()
        if heading.startswith("part b"):
            in_part_b = True
            structure_recognized = True
            if current_suggestion:
                part_b.append("\n".join(current_suggestion))
                current_suggestion = []
            continue
        if heading.startswith("part a"):
            structure_recognized = True
            in_part_b = False
            continue
        if stripped.startswith("```") and in_part_b:
            continue  # Skip code blocks in Part B
        if in_part_b:
            if stripped.startswith("SUGGESTION:") or stripped.startswith("CONTEXT:") or stripped.startswith("FIX:"):
                current_suggestion.append(stripped)

    if current_suggestion:
        part_b.append("\n".join(current_suggestion))

    return {
        "part_a": part_a,
        "part_b": part_b,
        "structure_recognized": structure_recognized,
    }


# ─── Notion DB helpers ───────────────────────────────────────────


def _load_skills_inventory(console: Console) -> str:
    """Read Skills & Keywords DB and format as a text list for prompts.

    Returns empty string if DB is unavailable — steps degrade gracefully.
    """
    try:
        from config import SKILLS_KEYWORDS_DB_ID
        if not SKILLS_KEYWORDS_DB_ID:
            return ""
        output = _run_script("notion_reader.py", ["database", SKILLS_KEYWORDS_DB_ID])
        entries = json.loads(output).get("entries", [])
        lines = []
        for e in entries:
            props = e.get("properties", {})
            name = props.get("Name", "")
            if not name:
                continue
            cat = props.get("Category") or ""
            prof = props.get("Proficiency") or ""
            priority = props.get("ATS Priority") or ""
            lines.append(f"- {name} | {cat} | {prof} | Priority: {priority}")
        return "\n".join(lines)
    except Exception as err:
        console.print(f"  [dim]Skills DB unavailable ({err}) — proceeding without.[/dim]")
        return ""


def _load_qa_templates(console: Console) -> str:
    """Read Q&A Templates DB and format for the Q&A generation prompt.

    Returns empty string if DB is empty or unavailable.
    """
    try:
        from config import QA_TEMPLATES_DB_ID
        if not QA_TEMPLATES_DB_ID:
            return ""
        output = _run_script("notion_reader.py", ["database", QA_TEMPLATES_DB_ID])
        entries = json.loads(output).get("entries", [])
        lines = []
        for e in entries:
            props = e.get("properties", {})
            question = props.get("Name", "")
            if not question:
                continue
            category = props.get("Category") or ""
            template = props.get("Template Answer") or ""
            notes = props.get("Notes") or ""
            block = f"**[{category}]** {question}"
            if template:
                block += f"\n{template}"
            if notes:
                block += f"\n*Notes: {notes}*"
            lines.append(block)
        return "\n\n".join(lines)
    except Exception as err:
        console.print(f"  [dim]Q&A Templates DB unavailable ({err}) — proceeding without.[/dim]")
        return ""


# ─── Step 5: ATS Check via LLM ───────────────────────────────────


def is_usable_ats_report(report: dict | None) -> bool:
    """True when a parsed ATS report carries the structure the pipeline uses.

    The existing downstream code dereferences ``json.coverage_score.coverage_pct``,
    so a payload lacking a ``coverage_score`` mapping is not a real ATS report even
    when it is valid truthy JSON (for example ``{"error": "cannot analyse"}``).
    """
    payload = (report or {}).get("json")
    return isinstance(payload, dict) and isinstance(
        payload.get("coverage_score"), dict
    )


def step_ats_check(ctx: dict, llm: LLMClient, console: Console) -> dict:
    if ctx.get("skip_ats"):
        console.print("\n[bold]ATS check:[/bold] [yellow]Skipped (--skip-ats)[/yellow]")
        ctx["ats_status"] = STAGE_SKIPPED
        ctx["ats_skip_reason"] = STAGE_SKIP_NOT_REQUESTED
        ctx["ats_report"] = {}
        return ctx

    console.print("\n[bold]Step 5/9:[/bold] Running ATS keyword check...")

    # Load skill inventory once per run (cached on ctx)
    if "skills_inventory" not in ctx:
        ctx["skills_inventory"] = _load_skills_inventory(console)

    skills_section = ""
    if ctx["skills_inventory"]:
        skills_section = (
            f"---\n\n"
            f"## Candidate Skill Inventory\n\n"
            f"Confirmed skills (Name | Category | Proficiency | ATS Priority). "
            f"Use this to classify N/A vs MISSING accurately — "
            f"only mark N/A if the skill is absent from this list:\n\n"
            f"{ctx['skills_inventory']}\n\n"
        )
        console.print(f"  Skill inventory loaded ({len(ctx['skills_inventory'].splitlines())} skills)")

    system_prompt = _load_prompt("ats_check")
    user_prompt = (
        f"## Job Posting\n\n"
        f"**Title:** {ctx['job']['title']}\n"
        f"**Company:** {ctx['job']['company']}\n\n"
        f"{ctx['job']['description']}\n\n"
        f"---\n\n"
        f"## Tailored Resume (.tex)\n\n"
        f"{ctx['tailored_latex']}\n\n"
        f"---\n\n"
        f"{skills_section}"
        f"Run the full ATS coverage and consistency check. "
        f"Output the JSON report between ```json and ``` markers, "
        f"then the Markdown report between ```markdown and ``` markers."
    )

    # B.1.5: the ATS stage owns its routing. ATS_PROVIDER/ATS_MODEL now control
    # this stage (previously they were ignored here and leaked into JD extraction).
    ats_llm = create_ats_client()
    with llm_telemetry.stage_context("ats", step_index=8) as st:
        try:
            raw = ats_llm.generate(system_prompt, user_prompt, temperature=0.2)
            ctx["ats_raw"] = raw
            report = parse_ats_report(raw)
            usable = is_usable_ats_report(report)
            st.set_parse_result(usable)
            if not usable:
                st.set_success(False)
            # A prose-only or malformed reply parses to no structured payload, and
            # valid JSON without the ATS structure the pipeline dereferences (for
            # example {"error": ...}) is not a usable semantic ATS report either.
            ctx["ats_status"] = STAGE_OK if usable else STAGE_FAILED
        except Exception as e:
            st.set_success(False)
            st.set_degradation("optional_stage_failed")
            console.print(f"  [yellow]ATS check failed ({e}). Continuing with no ATS edits.[/yellow]")
            ctx["ats_status"] = STAGE_FAILED
            report = {
                "json": {
                    "company": ctx["job"]["company"],
                    "job_title": ctx["job"]["title"],
                    "coverage_score": {"coverage_pct": 50, "verdict": "SKIPPED"},
                    "suggested_edits": [],
                    "consistency": {},
                },
                "markdown": (
                    f"# ATS Check: {ctx['job']['company']} - {ctx['job']['title']}\n\n"
                    f"Coverage: SKIPPED — all LLM providers rejected the payload.\n"
                    f"Verdict: SKIPPED\n"
                ),
            }

    ctx["ats_report"] = report

    # Save reports
    run_dir = Path(ctx["run_dir"])
    if report.get("json"):
        (run_dir / f"ats_report_{ctx['company_safe']}.json").write_text(
            json.dumps(report["json"], indent=2)
        )
    if report.get("markdown"):
        (run_dir / f"ats_report_{ctx['company_safe']}.md").write_text(
            report["markdown"]
        )

    # Display summary
    score = (report.get("json") or {}).get("coverage_score", {})
    pct = score.get("coverage_pct", "?")
    verdict = score.get("verdict", "UNKNOWN")
    console.print(f"  Coverage: {pct}% — Verdict: [bold]{verdict}[/bold]")

    return ctx


# ─── Score Application ──────────────────────────────────────────


def compute_pipeline_score(ctx: dict, console: Console) -> float:
    """Compute a 0-100 fit score from data the pipeline already generated.

    No new LLM calls. Uses ATS coverage (step 5), brief compliance (step 3c),
    company research depth (step 8), AI signal detection, and resume variant.

    Returns score 0-100.
    """
    scores = {}

    # ATS keyword coverage (40%)
    ats_json = (ctx.get("ats_report", {}).get("json") or {})
    ats_pct = ats_json.get("coverage_score", {}).get("coverage_pct", 50)
    if isinstance(ats_pct, str):
        ats_pct = int(ats_pct) if ats_pct.isdigit() else 50
    scores["ats"] = min(ats_pct, 100)

    # Brief compliance (20%)
    review = ctx.get("tailor_review", "").upper()
    if review.startswith("PASS"):
        scores["compliance"] = 100
    elif "SEVERITY: HIGH" in review:
        scores["compliance"] = 50
    elif review:
        scores["compliance"] = 75
    else:
        scores["compliance"] = 60

    # Company research depth (20%)
    research = ctx.get("company_research", "")
    scores["research"] = 100 if len(research) > 500 else 50 if research else 30

    # AI signal match (10%)
    ai_detected = _is_ai_heavy_jd(ctx.get("job", {}).get("description", ""))
    scores["ai"] = 100 if ai_detected else 50

    # Resume variant quality — user-selected (10%)
    scores["variant"] = 100

    # Weighted total
    total = (
        scores["ats"] * 0.40
        + scores["compliance"] * 0.20
        + scores["research"] * 0.20
        + scores["ai"] * 0.10
        + scores["variant"] * 0.10
    )

    ctx["pipeline_score"] = round(total)
    ctx["pipeline_score_breakdown"] = scores

    # Label
    s = ctx["pipeline_score"]
    if s >= 80:
        label = "STRONG"
        style = "green"
    elif s >= 60:
        label = "GOOD"
        style = "yellow"
    elif s >= 40:
        label = "WEAK"
        style = "yellow"
    else:
        label = "SKIP"
        style = "red"

    ctx["pipeline_score_label"] = label

    console.print(
        f"  Pipeline Score: [{style}]{s}/100 — {label}[/{style}] "
        f"(ATS:{scores['ats']} C:{scores['compliance']} "
        f"R:{scores['research']} AI:{scores['ai']} V:{scores['variant']})"
    )

    return total


# ─── Step 6: Apply ATS Edits ─────────────────────────────────────


def step_apply_ats_edits(
    ctx: dict, llm: LLMClient, console: Console
) -> dict:
    console.print("\n[bold]Step 6/9:[/bold] Reviewing ATS edits...")

    report = ctx.get("ats_report", {})
    ats_json = report.get("json") or {}
    edits = ats_json.get("suggested_edits", [])
    score = ats_json.get("coverage_score", {})
    pct = score.get("coverage_pct", 0)

    if not edits:
        console.print("  No edits suggested.")
        return ctx

    # Show the markdown report
    md = report.get("markdown", "")
    if md:
        console.print(Panel(Markdown(md), title="ATS Report", border_style="blue"))

    # Decide whether to auto-apply
    # Check if running interactively (has TTY) or from UI subprocess
    import sys
    is_interactive = sys.stdin.isatty()

    if pct >= 80:
        console.print(
            f"  [green]Score {pct}% >= 80% — auto-applying {len(edits)} edits.[/green]"
        )
        apply = True
    elif not is_interactive:
        # Running from UI - can't ask for input, auto-apply with warning
        console.print(f"  [yellow]Score {pct}% < 80% — auto-applying {len(edits)} edits (non-interactive mode).[/yellow]")
        for i, edit in enumerate(edits[:3], 1):
            console.print(f"  Edit {i}: [{edit.get('type', '?')}] {edit.get('keyword', '?')}")
        if len(edits) > 3:
            console.print(f"  ... and {len(edits) - 3} more edits")
        apply = True
    else:
        # Interactive terminal - ask user
        console.print(f"  [yellow]Score {pct}% < 80% — review needed.[/yellow]\n")
        for i, edit in enumerate(edits, 1):
            console.print(
                f"  Edit {i}: [[bold]{edit.get('type', '?')}[/bold]] "
                f"{edit.get('keyword', '?')}"
            )
            console.print(f"    Before: {edit.get('current_text', '')[:80]}")
            console.print(f"    After:  {edit.get('suggested_text', '')[:80]}")
            console.print(f"    Why:    {edit.get('rationale', '')}\n")
        apply = Confirm.ask("  Apply all suggested edits?", default=True)

    if not apply:
        console.print("  Skipped edits.")
        return ctx

    ctx["pre_ats_latex"] = ctx["tailored_latex"]
    targeted_mode = os.getenv("TARGETED_EDITS", "1") != "0"
    updated, applied, skipped = apply_grounded_ats_edits(
        ctx["tailored_latex"], edits, ctx["master_resume"], targeted=targeted_mode
    )
    ctx["tailored_latex"] = updated
    Path(ctx["tex_path"]).write_text(updated)
    console.print(
        f"  [green]Applied {applied} localized ATS edit(s); "
        f"skipped {skipped} unsupported or non-exact edit(s).[/green]"
    )

    integrity_errors = validate_resume_draft(updated, ctx["master_resume"])
    if integrity_errors:
        console.print(
            f"  [yellow]Factual-integrity validator rejected ATS result: "
            f"{'; '.join(integrity_errors[:4])}[/yellow]"
        )
        ctx["tailored_latex"] = ctx.get("pre_ats_latex", updated)
        Path(ctx["tex_path"]).write_text(ctx["tailored_latex"])

    return ctx


# ─── Step 7: Compile PDF ─────────────────────────────────────────


def step_compile_pdf(ctx: dict, llm: LLMClient, console: Console) -> dict:
    console.print("\n[bold]Step 7/9:[/bold] Compiling PDF...")

    result = compile_and_inspect(ctx["tex_path"], doc_type="cv")

    if not result.get("ok"):
        error = result.get("error", "Unknown error")
        for line in result.get("details", [])[:5]:
            console.print(f"  [red]{line}[/red]")
        raise RuntimeError(f"PDF compilation failed: {error}")

    ctx["pdf_path"] = result["pdf_path"]
    console.print(f"  [green]PDF: {result['pdf_path']}[/green]")
    if result.get("fixes"):
        console.print(f"  [yellow]Auto-fixes applied: {', '.join(result['fixes'])}[/yellow]")
    if result.get("warning"):
        console.print(f"  [yellow]{result['warning']}[/yellow]")
    return ctx


# ─── Sendability Gate (deterministic, no LLM) ──────────────────────


def step_evaluate_sendability(ctx: dict, llm: LLMClient, console: Console) -> dict:
    """Decide whether this generated package is safe to move to ready_to_apply.

    Deterministic only: no LLM call influences the verdict. This step never
    aborts the pipeline. If evaluation fails unexpectedly it leaves
    ``ctx["sendability"]`` unset, which the tracker write paths treat as
    "do not promote".
    """
    console.print("\n[bold]Sendability gate:[/bold] checking package readiness...")

    run_dir = Path(ctx["run_dir"])

    def _exists(path: Path | None) -> bool:
        if path is None:
            return False
        try:
            return path.is_file()
        except OSError:
            return False

    def _size(path: Path | None) -> int:
        if path is None:
            return 0
        try:
            return path.stat().st_size if path.is_file() else 0
        except OSError:
            return 0

    def _read(path: Path | None) -> str:
        if path is None:
            return ""
        try:
            return path.read_text() if path.is_file() else ""
        except OSError:
            return ""

    tex_path = Path(ctx["tex_path"]) if ctx.get("tex_path") else None
    pdf_path = Path(ctx["pdf_path"]) if ctx.get("pdf_path") else None
    template_path = PROJECT_ROOT / "templates" / "resume.tex"

    try:
        result = sendability.evaluate_sendability(
            run_id=ctx.get("run_id") or run_dir.name,
            final_latex=_read(tex_path),
            resume_artifact_present=_exists(tex_path),
            resume_artifact_bytes=_size(tex_path),
            pdf_present=_exists(pdf_path),
            pdf_bytes=_size(pdf_path),
            master_resume=ctx.get("master_resume"),
            canonical_template=_read(template_path) or None,
            tailoring_mode=ctx.get("tailoring_mode"),
            tailoring_outcome=ctx.get("tailoring_outcome"),
            tailoring_noop_reference=ctx.get("tailoring_noop_reference"),
            reviewer_failed=ctx.get("reviewer_status") == STAGE_FAILED,
            ats_semantic_unavailable=ctx.get("ats_status") == STAGE_FAILED,
            reviewer_skipped=ctx.get("reviewer_status") == STAGE_SKIPPED,
            ats_semantic_skipped=ctx.get("ats_status") == STAGE_SKIPPED,
            # Live Pilot Hotfix H1: candidate-controlled evidence only. The JD and
            # every model stage's output are deliberately excluded, so no stage can
            # certify a claim it introduced itself.
            skills_inventory=ctx.get("skills_inventory"),
            career_config=_career_config_evidence(),
            story_bank=_load_story_bank_evidence(),
            jd_skill_terms=_jd_skill_terms(ctx),
        )
    except Exception as err:  # never block the pipeline on the gate itself
        console.print(
            f"  [yellow]Sendability evaluation failed ({err}); not promoting.[/yellow]"
        )
        return ctx

    ctx["sendability"] = result

    try:
        report_path = sendability.write_sendability_report(run_dir, result)
        console.print(f"  Report: {report_path}")
    except OSError as err:
        console.print(f"  [yellow]Could not write sendability report: {err}[/yellow]")

    style = {
        sendability.READY_TO_SEND: "green",
        sendability.READY_WITH_WARNINGS: "yellow",
        sendability.HOLD: "red",
    }.get(result["status"], "white")
    console.print(f"  Status: [{style}]{result['status']}[/{style}]")
    for blocker in result["blockers"]:
        console.print(
            "    [red]BLOCKER[/red] "
            + escape_markup(f"{blocker['code']}: {blocker['detail']}")
        )
    for warning in result["warnings"]:
        console.print(
            "    [yellow]WARNING[/yellow] "
            + escape_markup(f"{warning['code']}: {warning['detail']}")
        )

    return ctx


# ─── Step 8: Generate Q&A ────────────────────────────────────────


# Stable marker for the synthetic cover-letter question. The cover-letter body is
# located by QUESTION IDENTITY (this marker, or an explicit cover-letter question),
# never by answer position.
COVER_LETTER_QUESTION_PREFIX = "Write a cover letter body for this application."

# The synthetic question forbids document metadata (date, greeting, sign-off) but
# not a content delimiter, and a delimiter is what makes the body machine-
# extractable when OTHER application questions were also asked: without it the
# reply parses as one Q/A pair whose answer swallows the letter as well, so the
# body could not be attributed without guessing.
COVER_LETTER_BODY_TAG_OPEN = "<cover_letter_body>"
COVER_LETTER_BODY_TAG_CLOSE = "</cover_letter_body>"
COVER_LETTER_TAG_INSTRUCTION = (
    f" Wrap the paragraphs in {COVER_LETTER_BODY_TAG_OPEN} and "
    f"{COVER_LETTER_BODY_TAG_CLOSE} tags."
)


def _load_cover_letter_quality_rules() -> str:
    """Load the cover-letter writing-quality contract (no-ai-slop adaptation).

    Cover-letter only: the fragment is appended to the synthetic cover-letter
    question, never to other Q&A prompts, so application answers keep their
    existing style. Optional by design, so a missing fragment degrades to the
    previous prompt instead of failing the stage.
    """
    try:
        return _load_prompt("cover_letter_writing_quality").strip()
    except OSError:
        return ""


def _strip_cover_letter_tags(text: str) -> str:
    """Remove the optional content delimiters from a candidate body."""
    return (
        text.replace(COVER_LETTER_BODY_TAG_OPEN, "")
        .replace(COVER_LETTER_BODY_TAG_CLOSE, "")
        .strip()
    )


def _find_delimited_cover_letter_body(raw: str) -> str | None:
    """Return the explicitly delimited cover-letter body, when the model honoured it."""
    match = re.search(
        re.escape(COVER_LETTER_BODY_TAG_OPEN)
        + r"(.*?)"
        + re.escape(COVER_LETTER_BODY_TAG_CLOSE),
        raw or "",
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None
    candidate = _strip_cover_letter_tags(match.group(1))
    return candidate if _looks_like_cover_letter_prose(candidate) else None


def _find_cover_letter_body(qa_pairs: list[dict]) -> str | None:
    """Return the cover-letter body by question identity, never by index."""
    for needle in (COVER_LETTER_QUESTION_PREFIX, "cover letter"):
        for pair in qa_pairs:
            question = str(pair.get("question") or "").lower()
            if needle.lower() in question:
                answer = str(pair.get("answer") or "").strip()
                if answer:
                    return answer
    return None


def _resolve_cover_letter_body(
    *, raw: str, qa_pairs: list[dict], real_questions: list[str]
) -> str | None:
    """Return the cover-letter body, or None when it genuinely is absent.

    Four deterministic routes, in order, all requiring the result to read as
    prose (never a refusal, scaffold or fragment):

    1. an explicit ``<cover_letter_body>`` block, which the synthetic question
       now requests so the body is attributable even when other questions were
       answered in the same reply;
    2. question identity (Gate A.4.1), so an unrelated Q&A answer can never be
       used;
    3. the residual of a reply that omits the question text entirely, which is
       what a compliance-optimal cover-letter-only run looks like (the prompt
       forbids echoing itself);
    4. nothing - a truthful failure, never a guess.
    """
    by_identity = _find_cover_letter_body(qa_pairs)
    if by_identity:
        return _strip_cover_letter_tags(by_identity)
    delimited = _find_delimited_cover_letter_body(raw)
    if delimited:
        return delimited
    return _cover_letter_body_from_unstructured_response(
        raw, qa_pairs, real_questions
    )


# A response that is a refusal or an apology is not a cover letter. Rejecting it
# keeps the failure truthful instead of shipping a non-body as the artifact.
_COVER_LETTER_REFUSAL_MARKERS = (
    "i can't",
    "i cannot",
    "i'm unable",
    "i am unable",
    "as an ai",
    "i don't have",
    "i do not have",
    "i need more information",
)


def _looks_like_cover_letter_prose(text: str) -> bool:
    """True when ``text`` reads as body paragraphs rather than scaffolding."""
    if len(text) < 50:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in _COVER_LETTER_REFUSAL_MARKERS):
        return False
    if re.match(r"^\s*(?:#{1,6}\s*)?(?:q|a)\s*:", lowered):
        return False
    return bool(re.search(r"[.!?](?:\s|$)", text))


def _cover_letter_body_from_unstructured_response(
    raw: str, qa_pairs: list[dict], real_questions: list[str]
) -> str | None:
    """Recover the cover-letter body from a response that omits the question.

    The synthetic question forbids echoing itself ("Output ONLY the body
    paragraphs ... Do NOT include a date line, greeting, sign-off, or any other
    metadata"), so a compliant response never carries the question text that
    identity matching needs. This is the one case where the reply must be read as
    the body.

    Attribution is still deterministic and cannot borrow another question's
    answer: every recognised answer is removed from the response by exact text
    match first, any leftover Q/A scaffolding is dropped, and what remains must
    look like prose. When nothing attributable remains, the result is ``None`` -
    a truthful failure, never a guess.
    """
    residual = str(raw or "")
    if not residual.strip():
        residual = "\n".join(
            str(pair.get("answer") or "") for pair in qa_pairs
        )

    # Remove only the answers attributable to REAL application questions. A
    # cover-letter-only reply is often parsed as one bogus "pair" whose answer
    # is most of the letter, so removing every parsed answer would destroy the
    # very body being recovered.
    normalised_questions = [
        re.sub(r"\s+", " ", question.strip().lower())
        for question in real_questions
        if question.strip()
    ]
    for pair in qa_pairs:
        question = re.sub(
            r"\s+", " ", str(pair.get("question") or "").strip().lower()
        )
        if not any(q and q in question for q in normalised_questions):
            continue
        answer = str(pair.get("answer") or "").strip()
        if answer and answer in residual:
            residual = residual.replace(answer, "", 1)
        # Drop the question text too, so a leftover "Why do you want this role?"
        # line cannot end up inside the cover letter.
        question_text = str(pair.get("question") or "").strip()
        if question_text and question_text in residual:
            residual = residual.replace(question_text, "", 1)

    residual = re.sub(r"(?m)^\s*#{1,6}\s*[QA][^:\n]*:\s*", "", residual)
    residual = re.sub(r"(?m)^\s*[QA]\s*:\s*", "", residual)
    residual = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", residual)
    residual = residual.strip()

    if residual.startswith("```"):
        residual = residual.strip("`").strip()
        residual = re.sub(r"^(?:markdown|latex|text)\s*", "", residual, flags=re.I)
        residual = residual.strip()
    if residual.startswith(COVER_LETTER_QUESTION_PREFIX):
        residual = residual[len(COVER_LETTER_QUESTION_PREFIX) :].strip(" :\n\t")

    return residual if _looks_like_cover_letter_prose(residual) else None


# ── Cover-letter deterministic style check (no-ai-slop enforcement) ──
#
# Prompt wording alone did not stop the model from returning the exact
# binary-contrast and metadiscourse forms the writing contract bans (the first
# real regeneration still opened with "growth problem is not demand. It is
# that..."). This is a small, HIGH-CONFIDENCE checker for COVER-LETTER BODIES
# ONLY. It names patterns the contract already lists; it is not an AI detector,
# does not score writing, and is never a factual guard. Conservatism is
# deliberate: a false positive is worse than a missed subtle stylistic issue,
# so only forms that carry no information AND match a named template report.

COVER_LETTER_STYLE_CLEAN = "clean"
COVER_LETTER_STYLE_CORRECTED = "corrected"
COVER_LETTER_STYLE_REVIEW = "needs_human_review"


@dataclass(frozen=True)
class CoverLetterStyleFinding:
    """One high-confidence cover-letter style violation."""

    code: str
    label: str
    snippet: str

    def as_dict(self) -> dict:
        return {"code": self.code, "label": self.label, "snippet": self.snippet}


# Binary contrast, cross-sentence: "<X> is not <Y>. It is <Z>." The punchline
# lives in the sentence after the negation, which is the shape upstream bans. The
# negation must be a copula ("is/was/'s not", "isn't") so ordinary prose such as
# "I am not sure the timeline is realistic" is never flagged.
_CROSS_SENTENCE_BINARY = re.compile(
    r"\b(?:is|are|was|were|['’]s)\s+not\b"
    r"[^.!?\n]{0,140}[.!?]\s+"
    r"(?:It|That|This)(?:['’]s|\s+(?:is|was|were|are))\b"
    r"|\b(?:isn['’]t|aren['’]t|wasn['’]t|weren['’]t)\b"
    r"[^.!?\n]{0,140}[.!?]\s+"
    r"(?:It|That|This)(?:['’]s|\s+(?:is|was|were|are))\b",
    re.IGNORECASE,
)
# "not just X, but Y" / "not merely X, but Y" / "not simply X, but Y".
_NOT_JUST_BUT = re.compile(
    r"\bnot\s+(?:just|merely|simply)\b[^.!?\n]{1,120}\bbut\b",
    re.IGNORECASE,
)
# Copula form "is not X, but Y". A bare "not X, but Y" is deliberately not
# matched: it is too easy to confuse with ordinary prose such as "I am not sure,
# but the timeline looks tight", and a false positive is worse here.
_COPULA_NOT_BUT = re.compile(
    r"\b(?:is|are|was|were|['’]s)\s+not\s+(?!only\b)[^.!?\n]{1,120},\s*but\b",
    re.IGNORECASE,
)
# "not because X, but because Y".
_NOT_BECAUSE_BUT = re.compile(
    r"\bnot\s+because\b[^.!?\n]{1,120}[,;]\s*but\s+because\b",
    re.IGNORECASE,
)
# "less about X, more about Y".
_LESS_MORE = re.compile(
    r"\bless\s+about\b[^.!?\n]{1,120}\bmore\s+about\b",
    re.IGNORECASE,
)

# Explicit interpretive metadiscourse markers.
_METADISCOURSE = re.compile(
    r"\b(?:the lesson|the takeaway|the key point|what this shows|this shows|"
    r"both experiences point|the part i recogni[sz]e|this is the part|"
    r"i have spent my career on exactly that surface|"
    r"this is exactly the kind of)\b",
    re.IGNORECASE,
)

# Invented company diagnosis, only when it opens the letter (anchored with
# ``.match`` against the stripped body). "X does not have a demand problem".
_FAUX_DIAGNOSIS = re.compile(
    r"[\w&.]+['’]s\b[^.!?\n]{0,90}\b(?:problem|challenge)\b\s+(?:is|was)\b",
    re.IGNORECASE,
)
_FAUX_NO_PROBLEM = re.compile(
    r"[\w&.]+['’]?s?\b\s+does\s+not\s+have\s+a\b[^.!?\n]{0,60}\bproblem\b",
    re.IGNORECASE,
)

# Sloganized abstractions that name a feeling instead of a mechanism. Only
# unambiguous phrases; bare "surface"/"layer"/"lever" stay unflagged because
# they are legitimate in moderation.
_SLOGAN_ABSTRACTION = re.compile(
    r"\b(?:are one funnel|as one system|the product decisions that move them|"
    r"where intent decays|the traffic-to-conversion surface)\b",
    re.IGNORECASE,
)

_BINARY_STYLE_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "binary_contrast_cross_sentence",
        "binary contrast: not X. It is Y.",
        _CROSS_SENTENCE_BINARY,
    ),
    (
        "binary_contrast_not_just_but",
        "binary contrast: not just X, but Y",
        _NOT_JUST_BUT,
    ),
    (
        "binary_contrast_is_not_but",
        "binary contrast: is not X, but Y",
        _COPULA_NOT_BUT,
    ),
    (
        "binary_contrast_not_because_but",
        "binary contrast: not because X, but because Y",
        _NOT_BECAUSE_BUT,
    ),
    (
        "binary_contrast_less_more",
        "binary contrast: less about X, more about Y",
        _LESS_MORE,
    ),
)

_OPENING_STYLE_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("faux_diagnosis", "invented company diagnosis opener", _FAUX_DIAGNOSIS),
    (
        "faux_diagnosis_no_problem",
        "invented company diagnosis opener: does not have a X problem",
        _FAUX_NO_PROBLEM,
    ),
)


def _style_snippet(text: str, start: int, end: int, *, width: int = 90) -> str:
    """Return a bounded, whitespace-collapsed snippet around a match."""
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    if len(snippet) > width:
        snippet = snippet[: width - 1].rstrip() + "..."
    return snippet


def check_cover_letter_style(body: str) -> list[CoverLetterStyleFinding]:
    """Return high-confidence no-ai-slop violations in a cover-letter body.

    Cover-letter only. Names patterns the writing contract already bans; never a
    factual guard, never an AI detector, never a quality score.
    """
    text = body or ""
    if not text.strip():
        return []

    findings: list[CoverLetterStyleFinding] = []
    seen: set[tuple[str, str]] = set()

    def add(code: str, label: str, match: re.Match[str]) -> None:
        snippet = _style_snippet(text, match.start(), match.end())
        key = (code, snippet.lower())
        if snippet and key not in seen:
            seen.add(key)
            findings.append(CoverLetterStyleFinding(code, label, snippet))

    for code, label, pattern in _BINARY_STYLE_RULES:
        for match in pattern.finditer(text):
            add(code, label, match)

    for match in _METADISCOURSE.finditer(text):
        add("metadiscourse", "interpretive metadiscourse", match)

    for match in _SLOGAN_ABSTRACTION.finditer(text):
        add("slogan_abstraction", "sloganized abstraction", match)

    opening = text.lstrip()
    for code, label, pattern in _OPENING_STYLE_RULES:
        match = pattern.match(opening)
        if match:
            findings.append(
                CoverLetterStyleFinding(
                    code,
                    label,
                    _style_snippet(opening, match.start(), match.end()),
                )
            )

    return findings


def _format_style_findings(findings: list[CoverLetterStyleFinding]) -> str:
    """Render findings for the correction prompt, names and snippets only."""
    return "\n".join(
        f'- {finding.code}: "{finding.snippet}"' for finding in findings
    )


def _load_cover_letter_style_correction_template() -> str:
    """Load the one-retry correction prompt. Missing file degrades to review."""
    try:
        return _load_prompt("cover_letter_style_correction").strip()
    except OSError:
        return ""


def _extract_corrected_cover_letter_body(raw: str) -> str | None:
    """Recover the corrected body from a correction reply."""
    delimited = _find_delimited_cover_letter_body(raw)
    if delimited:
        return delimited
    return None


# Numeric tokens (with optional percent) used to prove a correction did not
# change, add or drop a metric. Commas are normalised away so "55,000" and
# "55000" compare equal; the sign/percent suffix is kept.
_NUMERIC_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?%?")

# Content words used to prove a correction is an edit of the SAME letter rather
# than a replacement letter. Lowercased alphabetic tokens of length >= 5.
_OVERLAP_TOKEN = re.compile(r"[A-Za-z]{5,}")


def _numeric_tokens(text: str) -> set[str]:
    return {
        token.replace(",", "")
        for token in _NUMERIC_TOKEN.findall(text or "")
        if token.strip(",")
    }


def _content_overlap(original: str, corrected: str) -> float:
    """Fraction of the original's content words that survive in the correction."""
    original_tokens = {t.lower() for t in _OVERLAP_TOKEN.findall(original or "")}
    if not original_tokens:
        return 1.0
    corrected_tokens = {t.lower() for t in _OVERLAP_TOKEN.findall(corrected or "")}
    return len(original_tokens & corrected_tokens) / len(original_tokens)


def _correction_preserves_facts(original: str, corrected: str) -> tuple[bool, dict]:
    """Editorial-safety check for a prune pass: no added or changed facts.

    The second call is a deletion-first prune. Two deterministic failures force
    human review instead of accepting an unsafe body:

    * a numeric token was ADDED or CHANGED relative to the original (a prune may
      drop a metric, but it may never introduce or substitute one);
    * the body materially grew (a prune deletes, it does not enrich), or fewer
      than half of the original's content words survive (the model replaced the
      letter rather than editing it).
    """
    original_counts = Counter(_numeric_tokens(original))
    corrected_counts = Counter(_numeric_tokens(corrected))
    introduced = sorted(set(corrected_counts) - set(original_counts))
    # Dropping a number is allowed; it is recorded for audit only.
    dropped = sorted(set(original_counts) - set(corrected_counts))
    # Catch an in-place substitution whose replacement value already appears
    # elsewhere in the draft (draft {30%, 45%} -> {45%, 45%} introduces no new
    # value but does change a metric).
    duplicated = sorted(
        token
        for token, count in corrected_counts.items()
        if count > original_counts.get(token, 0)
    )
    overlap = _content_overlap(original, corrected)
    grew = len(corrected.strip()) > len(original.strip()) * 1.05
    ok = not introduced and not duplicated and not grew and overlap >= 0.5
    detail = {
        "introduced_numbers": introduced,
        "dropped_numbers": dropped,
        "duplicated_numbers": duplicated,
        "content_overlap": round(overlap, 3),
        "length_grew": grew,
    }
    return ok, detail


def enforce_cover_letter_style(
    *, body: str | None, llm: LLMClient, console: Console
) -> tuple[str | None, dict]:
    """Check a cover-letter body, then run exactly ONE mandatory prune pass.

    Returns ``(final_body, status)``. The second call is always made for a
    non-empty cover-letter body, on the SAME routed client that drafted it. It is
    deletion-first: it may remove evidence and wording but may not add factual
    content. The pruned body is accepted only when the deterministic style
    checker is clean and the factual-preservation guard passes; otherwise the
    first-pass body is kept and the run is flagged for human review. There is
    never a third call.
    """
    status: dict = {
        "status": COVER_LETTER_STYLE_CLEAN,
        "first_pass_findings": [],
        "final_findings": [],
        "retry_triggered": False,
        "prune_pass": False,
        "prune_findings": [],
        "prune_changed": False,
        "model_calls": 1,
        "review_required": False,
    }
    if not body or not body.strip():
        return body, status

    first_pass = check_cover_letter_style(body)
    status["first_pass_findings"] = [f.as_dict() for f in first_pass]
    status["prune_findings"] = [f.as_dict() for f in first_pass]

    template = _load_cover_letter_style_correction_template()
    if not template:
        status.update(
            status=COVER_LETTER_STYLE_REVIEW,
            final_findings=[f.as_dict() for f in first_pass],
            review_required=True,
            factual_guard="prune_prompt_missing",
            prune_rejected_reason="prune_prompt_missing",
        )
        console.print(
            "  [yellow]Cover letter prune pass: prompt missing; "
            "flagged for human review.[/yellow]"
        )
        return body, status

    # Mandatory, bounded: one generation call already happened upstream, this
    # adds exactly one prune call on the same client.
    status["prune_pass"] = True
    status["retry_triggered"] = True
    status["model_calls"] = 2
    findings_text = _format_style_findings(first_pass) or (
        "- (none detected: still remove any remaining banned construction and "
        "prune excess or tangential evidence, keeping every supported fact)"
    )
    prune_prompt = template.replace("{findings}", findings_text).replace(
        "{body}", body
    )
    try:
        prune_raw = llm.generate(
            "You are a ruthless copy editor. Prune the supplied cover letter "
            "body; do not enrich it. Return only the pruned body.",
            prune_prompt,
            temperature=0.3,
        )
    except Exception as err:
        status.update(
            status=COVER_LETTER_STYLE_REVIEW,
            final_findings=[f.as_dict() for f in first_pass],
            review_required=True,
            prune_rejected_reason="prune_call_failed",
        )
        console.print(
            f"  [yellow]Cover letter prune pass failed ({err}); "
            "flagged for human review.[/yellow]"
        )
        return body, status

    pruned = _extract_corrected_cover_letter_body(prune_raw)
    if not pruned:
        status.update(
            status=COVER_LETTER_STYLE_REVIEW,
            final_findings=[f.as_dict() for f in first_pass],
            review_required=True,
            prune_rejected_reason="prune_unparseable",
        )
        console.print(
            "  [yellow]Cover letter prune pass could not be parsed; "
            "flagged for human review.[/yellow]"
        )
        return body, status

    # Editorial safety: the prune may delete, but it may not add a number,
    # substitute a metric, materially grow the body, or replace the letter.
    preserves, guard_detail = _correction_preserves_facts(body, pruned)
    if not preserves:
        status.update(
            status=COVER_LETTER_STYLE_REVIEW,
            final_findings=[f.as_dict() for f in first_pass],
            review_required=True,
            factual_guard="correction_did_not_preserve_facts",
            factual_guard_detail=guard_detail,
            rejected_correction=pruned,
            prune_rejected_reason="prune_changed_or_added_facts",
        )
        console.print(
            "  [yellow]Cover letter prune pass changed or added facts; kept "
            "the draft and flagged for human review.[/yellow]"
        )
        return body, status

    final_findings = check_cover_letter_style(pruned)
    status["final_findings"] = [f.as_dict() for f in final_findings]
    if final_findings:
        status.update(
            status=COVER_LETTER_STYLE_REVIEW,
            review_required=True,
            rejected_correction=pruned,
            prune_rejected_reason="still_dirty",
        )
        console.print(
            "  [yellow]Cover letter prune pass left high-confidence patterns; "
            "kept the draft and flagged for human review (no further retry)."
            "[/yellow]"
        )
        return body, status

    status["status"] = (
        COVER_LETTER_STYLE_CORRECTED if first_pass else COVER_LETTER_STYLE_CLEAN
    )
    status["prune_changed"] = pruned.strip() != body.strip()
    console.print(
        "  [green]Cover letter prune pass accepted"
        + (" (body tightened)." if status["prune_changed"] else " (body unchanged).")
        + "[/green]"
    )
    return pruned, status


def step_generate_qa(ctx: dict, llm: LLMClient, console: Console) -> dict:
    # Deterministic requirement signals. The cover-letter body request injected
    # below is a synthetic question, so qa_required reflects real application
    # questions only.
    real_questions = [
        q for q in ctx.get("all_questions", []) if isinstance(q, str) and q.strip()
    ]
    cover_letter_required = bool(ctx.get("generate_cover_letter"))
    ctx["qa_required"] = bool(real_questions)
    ctx["cover_letter_required"] = cover_letter_required

    if not real_questions and not cover_letter_required:
        # Nothing to answer and no cover letter requested: make no writing call.
        console.print(
            "\n[bold]Q&A:[/bold] [yellow]Skipped: no application questions[/yellow]"
        )
        ctx["qa_status"] = STAGE_SKIPPED
        ctx["qa_skip_reason"] = STAGE_SKIP_NO_APPLICATION_QUESTIONS
        ctx["qa_answers"] = []
        return ctx

    # Prepend cover letter question if requested
    if cover_letter_required:
        # Avoid duplication if user already typed "cover letter" in questions
        all_q = ctx.get("all_questions", [])
        already_has_cl = any(
            "cover letter" in q.lower() for q in all_q
        )
        if not already_has_cl:
            cl_instructions = ctx.get("cover_letter_instructions", "").strip()
            cl_quality = _load_cover_letter_quality_rules()
            cl_q = COVER_LETTER_QUESTION_PREFIX + " Output ONLY the body paragraphs (2-4 paragraphs). Do NOT include a date line, greeting, sign-off, or any other metadata, only the paragraphs themselves. The LaTeX template supplies the greeting and sign-off." + COVER_LETTER_TAG_INSTRUCTION
            if cl_quality:
                # Writing-quality contract, scoped to the cover letter only.
                cl_q += "\n\n" + cl_quality
            if cl_instructions:
                cl_q += f" Additional instructions: {cl_instructions}"
            all_q.insert(0, cl_q)
            ctx["all_questions"] = all_q

    questions = ctx.get("all_questions", [])
    if not questions:
        console.print("\n[bold]Q&A:[/bold] No questions — skipping.")
        ctx["qa_status"] = STAGE_SKIPPED
        ctx["qa_skip_reason"] = STAGE_SKIP_NO_APPLICATION_QUESTIONS
        ctx["qa_answers"] = []
        return ctx

    console.print(
        f"\n[bold]Step 8/9:[/bold] Generating answers for "
        f"{len(questions)} questions..."
    )

    # Company research - use direct URL if provided, otherwise search
    # Optional research, used only to enrich the writing prompt. A failure here
    # must not abort the run.
    company_url = ctx.get("company_url")
    company_name = ctx["job"].get("company", "")
    try:
        company_research = research_company(
            company_name, company_url=company_url, console=console
        )
    except Exception as err:
        console.print(f"  [dim]Company research skipped: {err}[/dim]")
        company_research = ""
    ctx["company_research"] = company_research

    # Load Q&A templates (cached on ctx; graceful empty fallback)
    if "qa_templates" not in ctx:
        ctx["qa_templates"] = _load_qa_templates(console)

    templates_section = ""
    if ctx["qa_templates"]:
        templates_section = (
            f"---\n\n"
            f"## Q&A Templates\n\n"
            f"Common question patterns with preferred answer structures. "
            f"Use these as style guides — do NOT copy verbatim, adapt to this specific role:\n\n"
            f"{ctx['qa_templates']}\n\n"
        )
        console.print("  Q&A templates loaded")

    from config import ROLE_VARIANT
    role_framing = {
        "growth_pm": (
            "Resume variant: **Growth PM**. "
            "Foreground growth and conversion experiences: Accenture (45% CVR, LatAm growth) "
            "and C&A Brasil (checkout optimisation, experimentation). "
            "Postscript for AI/ML depth. HELLA as secondary."
        ),
        "generalist": (
            "Resume variant: **Generalist PM**. "
            "Foreground full product lifecycle and stakeholder management: FORVIA HELLA "
            "(B2B platform, roadmap, cross-functional delivery, €12M revenue). "
            "Accenture and C&A as supporting evidence of execution breadth."
        ),
        "ai_pm": (
            "Resume variant: **AI PM**. "
            "Postscript is the primary story: AI-powered message optimization (28% earnings-per-message lift, predictive analytics, generative AI), SMS compliance optimization (32% opt-in conversion increase), and analytics instrumentation across 18,000+ merchant accounts."
            "LLM evaluation and governance), AI validation platform (non-technical ML experiments "
            "at scale, use case prioritisation), and analytics for 20+ country programs. "
            "Foreground the agentic PM workflow (Cursor, Claude Code, MCP) as a differentiator. "
            "HELLA for platform and B2B depth. Accenture and C&A as execution breadth."
        ),
    }.get(ROLE_VARIANT, "")

    writing_llm = create_qa_client()
    system_prompt = _load_voice_prefix() + _load_prompt("qa_generator")
    questions_text = "\n".join(
        f"{i + 1}. {q.strip()}" for i, q in enumerate(questions)
    )

    qa_ai_context_section = ""
    qa_ai_pm_variant = (ROLE_VARIANT == "ai_pm")
    if qa_ai_pm_variant or _is_ai_heavy_jd(ctx['job']['description']):
        ai_ctx = _load_ai_pm_context()
        if ai_ctx:
            qa_ai_context_section = (
                f"## Candidate AI PM Context\n\n"
                f"The role has AI tool/workflow requirements. Draw from the context below "
                f"when answering questions about AI tool usage, AI-augmented workflows, "
                f"or how the candidate works with AI. Use specific examples grounded in "
                f"the Postscript period and the JobQuest pipeline where relevant.\n\n"
                f"{ai_ctx}\n\n"
                f"---\n\n"
            )

    # Load behavioral profile (optional — graceful empty fallback)
    behavioral_profile = _load_behavioral_profile()

    salary_benchmark = ctx.get("salary_benchmark")

    # Static/semi-static content first (cached by DeepSeek prefix cache),
    # dynamic content last (changes per application, always after the cached prefix).
    user_prompt = (
        f"## Master Resume\n\n{ctx['master_resume']}\n\n"
        f"---\n\n"
        f"{templates_section}"
        f"---\n\n"
        f"{qa_ai_context_section}"
        + (f"## Behavioral Profile\n\n{behavioral_profile}\n\n---\n\n" if behavioral_profile else "")
        + f"## Job Posting\n\n"
        f"**Title:** {ctx['job']['title']}\n"
        f"**Company:** {ctx['job']['company']}\n\n"
        f"{ctx['job']['description'][:3000]}\n\n"
        f"---\n\n"
        f"## Company Research\n\n{company_research[:2000]}\n\n"
        f"---\n\n"
        + (_build_salary_qa_section(salary_benchmark) if salary_benchmark else "")
        + f"## Questions to Answer\n\n{questions_text}\n\n"
        f"---\n\n"
        f"{role_framing}\n\n"
        f"Generate answers for each question."
    )

    with llm_telemetry.stage_context("qa_cover_letter", step_index=12) as st:
        try:
            raw = writing_llm.generate(system_prompt, user_prompt, temperature=0.7)
            ctx["qa_raw"] = raw
        except Exception as err:
            # Q&A is optional relative to the resume package: never abort the run.
            st.set_success(False)
            st.set_degradation("optional_stage_failed")
            console.print(
                f"  [yellow]Q&A generation failed ({err}), continuing without answers.[/yellow]"
            )
            ctx["qa_answers"] = []
            if real_questions:
                ctx["qa_status"] = STAGE_FAILED
            else:
                ctx["qa_status"] = STAGE_SKIPPED
                ctx["qa_skip_reason"] = STAGE_SKIP_NO_APPLICATION_QUESTIONS
            return ctx

        qa_pairs = parse_qa_answers(raw)
        st.set_parse_result(bool(qa_pairs))
        if not qa_pairs and real_questions:
            st.set_success(False)
        ctx["qa_answers"] = qa_pairs
        if real_questions:
            # A call that produced no usable parsed answer is a failure, not a pass.
            ctx["qa_status"] = STAGE_OK if qa_pairs else STAGE_FAILED
        else:
            # Only the cover-letter body was requested; Q&A itself was not required.
            ctx["qa_status"] = STAGE_SKIPPED
            ctx["qa_skip_reason"] = STAGE_SKIP_NO_APPLICATION_QUESTIONS

        # Cover-letter body resolution plus the deterministic no-ai-slop check.
        # The check may spend ONE additional correction call, on the SAME routed
        # client that produced the draft (bounded: two cover-letter calls total,
        # no new stage, no second provider chain). A body that is still dirty
        # after the correction is surfaced for human review, never accepted.
        if cover_letter_required:
            body = _resolve_cover_letter_body(
                raw=raw, qa_pairs=qa_pairs, real_questions=real_questions
            )
            body, cl_style = enforce_cover_letter_style(
                body=body, llm=writing_llm, console=console
            )
            ctx["cover_letter_body"] = body
            ctx["cover_letter_style"] = cl_style
        else:
            ctx["cover_letter_body"] = None

    # Save Q&A output
    run_dir = Path(ctx["run_dir"])
    # Optional artifacts: best-effort, never fatal.
    try:
        (run_dir / f"qa_{ctx['company_safe']}.md").write_text(raw)
    except OSError as err:
        console.print(f"  [dim]Could not write Q&A artifact: {err}[/dim]")

    # Save form-data JSON for form_filler
    from config import (
        APPLICANT_EMAIL,
        APPLICANT_LINKEDIN,
        APPLICANT_LOCATION,
        APPLICANT_NAME,
        APPLICANT_PHONE,
    )

    name_parts = (APPLICANT_NAME or "").split()
    form_data = {
        "name": APPLICANT_NAME,
        "first_name": name_parts[0] if name_parts else "",
        "last_name": name_parts[-1] if len(name_parts) > 1 else "",
        "email": APPLICANT_EMAIL,
        "phone": APPLICANT_PHONE,
        "linkedin": APPLICANT_LINKEDIN,
        "location": APPLICANT_LOCATION,
    }
    # Only a cover letter that was actually requested may populate the
    # cover-letter form field, and only from its own associated answer.
    cover_letter_body = ctx.get("cover_letter_body")
    if cover_letter_required and cover_letter_body:
        form_data["cover_letter"] = cover_letter_body

    form_path = run_dir / f"form_data_{ctx['company_safe']}.json"
    try:
        form_path.write_text(json.dumps(form_data, indent=2))
        ctx["form_data_path"] = str(form_path)
    except OSError as err:
        console.print(f"  [dim]Could not write form data: {err}[/dim]")

    console.print(f"  Generated {len(qa_pairs)} answers")
    for qa in qa_pairs:
        console.print(f"    Q: {qa['question'][:60]}...")

    return ctx


# ─── Step 8b: Generate Interview Prep ────────────────────────────


def step_generate_interview_prep(ctx: dict, llm: LLMClient, console: Console) -> dict:
    """Generate a structured interview prep document from pipeline context.

    Runs after Q&A generation (step 8), reusing company research context.
    Matches STAR stories from the story bank to JD requirements, generates
    likely interview questions, and saves the output to the run directory.

    Interview prep is post-application / on-demand work: it only runs when the
    run explicitly requests it, so a normal application generation makes no
    interview-prep LLM call and writes no interview-prep artifact.
    """
    if not ctx.get("interview_prep_requested"):
        console.print(
            "\n[bold]Interview prep:[/bold] [yellow]Skipped: not requested[/yellow]"
        )
        ctx["interview_prep_status"] = STAGE_SKIPPED
        ctx["interview_prep_skip_reason"] = STAGE_SKIP_NOT_REQUESTED
        return ctx

    console.print("\n[bold]Step 8b/10:[/bold] Generating interview prep...")

    run_dir = Path(ctx["run_dir"])
    company = ctx["job"].get("company", "Unknown")
    company_safe = ctx.get("company_safe", _safe_filename(company))

    # Load story bank (empty string if file missing)
    story_bank_path = PROJECT_ROOT / "interview-prep" / "story-bank.md"
    story_bank = ""
    if story_bank_path.exists():
        story_bank = story_bank_path.read_text()
        if len(story_bank) > 100:
            console.print(f"  Story bank loaded: {len(story_bank)} chars")
    else:
        console.print("  [dim]No story bank found — skipping STAR matching.[/dim]")

    # Build prompt with all available context
    writing_llm = create_interview_client()
    system_prompt = _load_prompt("interview_prep")

    company_research = ctx.get("company_research", "")
    jd_text = ctx["job"].get("description", "")
    master_resume = ctx.get("master_resume", "")

    # Include Q&A answers if available (for consistency)
    qa_section = ""
    qa_answers = ctx.get("qa_answers", [])
    if qa_answers:
        qa_lines = ["## Q&A Answers (for context — do not duplicate)"]
        for qa in qa_answers:
            q = qa.get("question", "")
            a = qa.get("answer", "")
            qa_lines.append(f"**Q:** {q}\n\n{a}\n")
        qa_section = "\n".join(qa_lines)

    user_prompt = (
        f"## Job Posting\n\n"
        f"**Title:** {ctx['job']['title']}\n"
        f"**Company:** {company}\n\n"
        f"{jd_text[:4000]}\n\n"
        f"---\n\n"
        f"## Company Research\n\n"
        f"{company_research[:3000] if company_research else 'No company research available.'}\n\n"
        f"---\n\n"
        f"## Master Resume\n\n"
        f"{master_resume[:3000]}\n\n"
    )

    # Story bank section (optional)
    if story_bank:
        user_prompt += (
            f"---\n\n"
            f"## Story Bank (STAR+R)\n\n"
            f"{story_bank}\n\n"
        )

    if qa_section:
        user_prompt += (
            f"---\n\n"
            f"{qa_section}\n\n"
        )

    user_prompt += "Generate the full interview preparation document."

    # Gate B.1: free-form prose stage (no structured parse outcome).
    with llm_telemetry.stage_context("interview_prep", step_index=13) as st:
        try:
            raw = writing_llm.generate(system_prompt, user_prompt, temperature=0.6)
            ctx["interview_prep_status"] = STAGE_OK
        except Exception as err:
            st.set_success(False)
            st.set_degradation("optional_stage_failed")
            console.print(f"  [yellow]Interview prep LLM call failed ({err}) — generating basic template.[/yellow]")
            raw = _fallback_interview_prep(ctx, story_bank)
            ctx["interview_prep_status"] = STAGE_FAILED

    # Save output
    filename = f"interview_prep_{company_safe}.md"
    output_path = run_dir / filename
    output_path.write_text(raw)
    ctx["interview_prep_path"] = str(output_path)

    console.print(f"  [green]Interview prep: {output_path}[/green]")
    return ctx


def _fallback_interview_prep(ctx: dict, story_bank: str) -> str:
    """Generate a basic interview prep template when the LLM call fails."""
    company = ctx["job"].get("company", "Unknown")
    title = ctx["job"].get("title", "Unknown")
    research = ctx.get("company_research", "")

    lines = [
        f"# Interview Preparation: {title} at {company}",
        "",
        "## Company Context",
        "",
        research if research.strip() else "No company research available.",
        "",
        "## Likely Questions",
        "",
        "### Technical / Role-Specific",
        "",
        "*No questions generated — LLM call failed. Review the JD manually.*",
        "",
        "### Behavioral",
        "",
        "*No questions generated — LLM call failed.*",
        "",
        "## Questions to Ask Them",
        "",
        "- What does success look like in the first 6 months?",
        "- How does the team divide work between PM, design, and engineering?",
        "- What do people who thrive here have in common?",
        "",
    ]

    if story_bank.strip():
        lines += [
            "## STAR Examples (Pre-Selected)",
            "",
            story_bank,
            "",
        ]

    lines += [
        "## Follow-Up Timeline",
        "",
        "- If no response after 2 weeks, send a brief follow-up.",
    ]

    return "\n".join(lines)


# ─── Step 9: Compile Cover Letter ──────────────────────────────────


# ─── Cover-letter formatting (deterministic, approved template) ───
#
# The writing model supplies body paragraphs only. Everything structural (title
# construction, location/date line, paragraph spacing) is rendered here so the
# output cannot drift from the approved template.

COVER_LETTER_PARAGRAPH_GAP = "\\vspace{10pt}"

# Separators a scraped posting title uses to embed the company name.
_COMPANY_SUFFIX_SEPARATORS = (" - ", " – ", " — ", " | ", " at ", ", ")


def _normalise_company_token(value: str) -> str:
    """Reduce a company name to comparable letters and digits.

    "Click&Boat" and "Clickboat" must compare equal, so punctuation, spacing and
    case are dropped before comparison. The display value keeps its own spelling.
    """
    return re.sub(r"[^0-9a-z]+", "", value.lower())


def split_role_and_company(job_title: str, company: str) -> tuple[str, str]:
    """Split a scraped posting title into (role, company display name).

    Scraped titles often embed the company name. The approved title is
    "Application for <role>, <company>", so a trailing segment that normalises
    to the scraped company is removed from the role and appended exactly once by
    the template. The posting's own spelling (for example "Click&Boat") wins
    over the normalised scrape value. At most one trailing segment is removed,
    so a hyphenated role is never damaged.
    """
    title = job_title.strip()
    target = _normalise_company_token(company)
    best: tuple[int, str] | None = None
    if target:
        for separator in _COMPANY_SUFFIX_SEPARATORS:
            index = title.rfind(separator)
            if index <= 0:
                continue
            candidate = title[index + len(separator):].strip()
            if _normalise_company_token(candidate) == target and (
                best is None or index > best[0]
            ):
                best = (index, candidate)
    if best is None:
        return title, company
    role = title[: best[0]].strip()
    return (role or title), best[1]


def _escape_cover_letter_text(text: str) -> str:
    """Escape LaTeX specials in generated prose.

    A body sentence containing '&', '%' or '_' previously injected raw LaTeX
    control characters and made pdflatex fail.
    """
    for char, replacement in (
        ("%", "\\%"),
        ("_", "\\_"),
        ("&", "\\&"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("~", "\\textasciitilde{}"),
        ("^", "\\textasciicircum{}"),
    ):
        text = text.replace(char, replacement)
    return text


def cover_letter_body_block(paragraphs: list[str]) -> str:
    """Join body paragraphs with the approved explicit 10pt paragraph gap."""
    return f"\n\n{COVER_LETTER_PARAGRAPH_GAP}\n\n".join(paragraphs)


def step_compile_cover_letter(ctx: dict, llm: LLMClient, console: Console) -> dict:
    """If cover letter was requested, extract body from Q&A and compile PDF."""
    if not ctx.get("generate_cover_letter"):
        ctx["cover_letter_status"] = STAGE_SKIPPED
        ctx["cover_letter_skip_reason"] = STAGE_SKIP_NOT_REQUESTED
        return ctx

    console.print("\n[bold]Step 9/10:[/bold] Compiling cover letter...")

    # The cover-letter body is located by question identity in step_generate_qa,
    # never positionally, so an unrelated Q&A answer cannot be used here.
    cover_body = (ctx.get("cover_letter_body") or "").strip()
    if not cover_body:
        console.print("  [yellow]No cover letter body was produced, skipping.[/yellow]")
        ctx["cover_letter_status"] = STAGE_FAILED
        return ctx
    if len(cover_body) < 50:
        console.print(f"  [yellow]Cover letter body too short ({len(cover_body)} chars), skipping.[/yellow]")
        ctx["cover_letter_status"] = STAGE_FAILED
        return ctx

    job_title = ctx["job"].get("title", "Unknown")
    company = ctx["job"].get("company", "Unknown")
    run_dir = Path(ctx["run_dir"])

    # Read template
    template_path = PROJECT_ROOT / "templates" / "cover_letter.tex"
    if not template_path.exists():
        console.print(f"  [red]Template not found: {template_path}[/red]")
        ctx["cover_letter_status"] = STAGE_FAILED
        return ctx
    try:
        template_text = template_path.read_text()
    except OSError as err:
        console.print(f"  [red]Could not read cover-letter template: {err}[/red]")
        ctx["cover_letter_status"] = STAGE_FAILED
        return ctx

    today = date.today()
    date_str = today.strftime("%d.%m.%Y")
    from config import APPLICANT_LOCATION
    # Approved date line is "Berlin, 13.10.2026": the city only, never the
    # country, so "Berlin, Germany" must not reach the template.
    place = (APPLICANT_LOCATION or "Berlin").split(",")[0].strip() or "Berlin"

    # Fill template (use .replace to avoid LaTeX brace conflicts with .format)
    # A template without the body placeholder would silently produce a bodiless
    # cover letter that still compiles, so refuse instead of faking success.
    if "{body}" not in template_text:
        console.print(
            f"  [red]Cover-letter template has no {{body}} placeholder: "
            f"{template_path}[/red]"
        )
        ctx["cover_letter_status"] = STAGE_FAILED
        return ctx

    # Title: the scrape often embeds the company in the posting title, which the
    # retired template then duplicated with its own ", at <company>" suffix.
    # Split it once here; the template appends the company exactly once.
    role_title, company_display = split_role_and_company(job_title, company)

    # Fill template (use .replace to avoid LaTeX brace conflicts with .format)
    # Substituted values are escaped: a posting title containing '&' (e.g.
    # "Traffic & Acquisition") previously injected a raw alignment character and
    # made the cover-letter compile fail.
    latex = template_text
    latex = latex.replace("{role_title}", escape_latex_text(role_title))
    latex = latex.replace("{company}", escape_latex_text(company_display))
    latex = latex.replace("{place}", escape_latex_text(place))
    latex = latex.replace("{date}", date_str)

    # Body paragraphs stay verbatim; only LaTeX specials are escaped, and the
    # approved inter-paragraph gap is inserted explicitly because \parskip is 0pt.
    cover_body = re.sub(r"\n?_Used:.*", "", cover_body)  # Strip Q&A tracking line
    body_paragraphs = [
        _escape_cover_letter_text(part.strip())
        for part in re.split(r"\n\s*\n", cover_body)
        if part.strip()
    ]
    if not body_paragraphs:
        console.print("  [red]Cover-letter body has no paragraphs; not writing.[/red]")
        ctx["cover_letter_status"] = STAGE_FAILED
        return ctx
    body_block = cover_letter_body_block(body_paragraphs)

    # Optional company motivation paragraph (forward-looking framing, Spec 002).
    # It renders as the first paragraph, so it carries its own trailing gap.
    company_paragraph = (ctx.get("cover_letter_company_paragraph") or "").strip()
    company_block = ""
    if company_paragraph:
        company_paragraph = _escape_cover_letter_text(
            re.sub(r"\n?_Used:.*", "", company_paragraph)
        )
        company_block = f"{company_paragraph}\n\n{COVER_LETTER_PARAGRAPH_GAP}\n\n"

    latex = latex.replace("{company_paragraph}", company_block)
    latex = latex.replace("{body}", body_block)

    # The requested artifact is only successful when the generated body is
    # actually in it, so verify the substitution landed before writing.
    if not all(paragraph in latex for paragraph in body_paragraphs):
        console.print(
            "  [red]Cover-letter body did not reach the template output; "
            "not writing.[/red]"
        )
        ctx["cover_letter_status"] = STAGE_FAILED
        return ctx

    # Write .tex file. A failure here is an optional-artifact failure, never a
    # run abort: the package must still reach sendability/tracker so the run is
    # recorded and the failure surfaces as a warning.
    tex_filename = "Cover-Letter_RodrigoLopes.tex"
    tex_path = run_dir / tex_filename
    try:
        tex_path.write_text(latex)
        written = tex_path.read_text()
    except OSError as err:
        console.print(f"  [red]Could not write cover-letter artifact: {err}[/red]")
        ctx["cover_letter_status"] = STAGE_FAILED
        return ctx
    if not all(paragraph in written for paragraph in body_paragraphs):
        console.print(
            f"  [red]Written cover-letter .tex does not contain the body: "
            f"{tex_path}[/red]"
        )
        ctx["cover_letter_status"] = STAGE_FAILED
        return ctx
    console.print(f"  [green]Written: {tex_path}[/green]")

    # Compile PDF with inspect-and-fix loop. Any failure here is an
    # optional-artifact failure, never a run abort: the package must still reach
    # sendability/tracker so the run is recorded and the failure becomes a
    # warning. This includes non-OSError failures such as a pdflatex timeout.
    try:
        result = compile_and_inspect(str(tex_path), doc_type="cover_letter")
    except Exception as err:  # noqa: BLE001 - documented optional-artifact guard
        console.print(f"  [red]Cover-letter compilation failed: {err}[/red]")
        ctx["cover_letter_status"] = STAGE_FAILED
        return ctx
    if result.get("ok"):
        # Success requires the final artifact to exist and be non-empty;
        # an LLM call that returned text is not by itself a delivered cover
        # letter.
        pdf_path = Path(result["pdf_path"])
        if not pdf_path.exists() or pdf_path.stat().st_size <= 0:
            console.print(
                f"  [red]Cover-letter PDF missing or empty after compile: "
                f"{pdf_path}[/red]"
            )
            ctx["cover_letter_status"] = STAGE_FAILED
            return ctx
        ctx["cover_letter_pdf_path"] = result["pdf_path"]
        ctx["cover_letter_status"] = STAGE_OK
        console.print(f"  [green]PDF: {result['pdf_path']}[/green]")
        if result.get("fixes"):
            console.print(f"  [yellow]Auto-fixes applied: {', '.join(result['fixes'])}[/yellow]")
        if result.get("warning"):
            console.print(f"  [yellow]{result['warning']}[/yellow]")
    else:
        error = result.get("error", "Unknown error")
        console.print(f"  [red]PDF compilation failed: {error}[/red]")
        ctx["cover_letter_status"] = STAGE_FAILED
        for line in result.get("details", [])[:3]:
            console.print(f"  [red]{line}[/red]")

    return ctx


# ─── Sendability finalization (deterministic, post-optional) ─────────


def step_finalize_sendability(ctx: dict, llm: LLMClient, console: Console) -> dict:
    """Fold late optional-stage failures into the persisted sendability report.

    Q&A, cover letter and interview prep run after the required sendability
    evaluation, so they cannot influence it. This is report/warning finalization
    only: no LLM call, no re-evaluation of required checks, no lifecycle change.
    ``HOLD`` is left exactly as it was, and a stage that was intentionally
    skipped produces nothing.
    """
    verdict = ctx.get("sendability")
    if not verdict:
        return ctx

    failures: dict[str, str] = {}
    if ctx.get("qa_status") == STAGE_FAILED:
        failures[sendability.WARN_QA_FAILED] = (
            "required application questions could not be answered"
        )
    if ctx.get("cover_letter_status") == STAGE_FAILED:
        failures[sendability.WARN_COVER_LETTER_FAILED] = (
            "requested cover letter could not be produced"
        )
    # The prune pass keeps the safe first-pass body and flags human review when
    # it cannot validate the cover-letter style. Surface that as an advisory so a
    # review-required cover letter is never silently READY_TO_SEND.
    if (ctx.get("cover_letter_style") or {}).get("review_required"):
        failures[sendability.WARN_COVER_LETTER_HUMAN_REVIEW_REQUIRED] = (
            "cover letter requires human review before sending"
        )
    if ctx.get("interview_prep_status") == STAGE_FAILED:
        failures[sendability.WARN_INTERVIEW_PREP_FAILED] = (
            "requested interview prep could not be produced"
        )

    updated = sendability.finalize_optional_stage_warnings(verdict, failures)
    if updated is verdict:
        return ctx

    ctx["sendability"] = updated
    try:
        sendability.write_sendability_report(Path(ctx["run_dir"]), updated)
    except OSError as err:
        console.print(f"  [yellow]Could not rewrite sendability report: {err}[/yellow]")
    console.print(f"  Finalized sendability: [bold]{updated['status']}[/bold]")
    return ctx


# ─── Step 10: Notion Tracking ────────────────────────────────────


def step_create_tracker_entry(
    ctx: dict, llm: LLMClient, console: Console
) -> dict:
    import sys

    if ctx.get("skip_notion"):
        console.print("\n[bold]Step 9/9:[/bold] Skipping tracker entry (--skip-notion).")
        return ctx

    console.print("\n[bold]Step 9/9:[/bold] Creating tracker entry...")
    sys.stdout.flush()

    job_title = ctx["job"].get("title") or "Unknown"
    company = ctx["job"].get("company") or "Unknown"
    job_url = ctx["job_url"]
    score = ctx.get("pipeline_score")
    score_label = ctx.get("pipeline_score_label", "")
    date_str = ctx.get("date", "") or __import__("datetime").date.today().isoformat()

    console.print(f"  Job: {job_title} at {company}")
    console.print(f"  Score: {score} ({score_label})")
    sys.stdout.flush()

    # Automatic promotion is decided by the deterministic sendability gate.
    # HOLD (or a missing/failed evaluation) leaves a new entry as ``generated``.
    promoted_status = sendability.promoted_tracker_status(
        (ctx.get("sendability") or {}).get("status")
    )

    entry = {
        "company": company,
        "role": job_title,
        "url": job_url,
        "score": score,
        "score_label": score_label,
        "date": date_str,
        "status": promoted_status,
        "notes": "",
    }

    apps_file = APPLICATIONS_FILE

    try:
        existing = []
        if apps_file.exists():
            existing = json.loads(apps_file.read_text())

        # Dedup: check if URL already exists (normalized)
        def normalize(u):
            return (u or "").rstrip("/").split("#")[0]

        norm_url = normalize(job_url)
        dup_idx = None
        for i, a in enumerate(existing):
            if normalize(a.get("url", "")) == norm_url:
                dup_idx = i
                break

        if dup_idx is not None:
            # Refresh generation metadata, and allow a forward-only move such as
            # generated -> ready_to_apply. ``resolve_tracker_status`` never
            # downgrades applied/screening/interview/offer/rejected, and never
            # writes ``applied`` by itself.
            existing[dup_idx].update({
                "score": score,
                "score_label": score_label,
                "date": date_str,
                "status": sendability.resolve_tracker_status(
                    existing[dup_idx].get("status"), promoted_status
                ),
            })
            console.print("  [yellow]↻ Updated existing tracker entry (duplicate URL)[/yellow]")
        else:
            existing.append(entry)
            console.print(f"  [green]✓ Added to tracker ({len(existing)} total)[/green]")

        apps_file.write_text(json.dumps(existing, indent=2))
        ctx["tracker_entry_created"] = True
    except Exception as e:
        console.print(f"  [red]✗ Tracker write error: {type(e).__name__}: {e}[/red]")
        console.print("  Continuing without tracker entry.")

    sys.stdout.flush()
    console.print("  [dim]Step 9/9 complete.[/dim]")
    return ctx


# ─── Step 10: Form Filler ────────────────────────────────────────


def step_run_form_filler(
    ctx: dict, llm: LLMClient, console: Console
) -> dict:
    if ctx.get("skip_form"):
        console.print("\n[bold]Step 10/10:[/bold] Skipping form filler (--skip-form).")
        return ctx

    console.print("\n[bold]Step 10/10:[/bold] Opening form filler...")
    console.print(
        "  [yellow]Browser will open. Review all fields, then submit manually.[/yellow]"
    )

    cmd = [VENV_PYTHON, str(SCRIPTS_DIR / "form_filler.py")]
    cmd += ["--url", ctx["job_url"]]
    if ctx.get("pdf_path"):
        cmd += ["--resume-pdf", ctx["pdf_path"]]
    if ctx.get("form_data_path"):
        cmd += ["--data-file", ctx["form_data_path"]]

    try:
        subprocess.run(cmd, timeout=300, cwd=str(PROJECT_ROOT))
    except subprocess.TimeoutExpired:
        console.print("  [yellow]Form filler timed out (5 min).[/yellow]")
    except Exception as e:
        console.print(f"  [red]Form filler error: {e}[/red]")

    console.print("  Form filler session complete.")
    return ctx
