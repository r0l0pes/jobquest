"""Pipeline step functions for the JobQuest orchestrator.

Each step takes a context dict (ctx), enriches it, and returns it.
Steps call existing scripts via subprocess or new modules directly.
"""

import subprocess
import os
import json
import re
import time
from pathlib import Path
from datetime import date

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Confirm
from rich.table import Table
from rich import box

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
from modules.parsers import extract_latex, fix_markdown_lists, parse_ats_report, parse_qa_answers, parse_resume_edits, apply_resume_edits
from scripts.render_pdf import compile_and_inspect

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
OUTPUT_DIR = PROJECT_ROOT / "output"
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


# ─── Step 1: Scrape Job Posting ──────────────────────────────────


def step_scrape_job(ctx: dict, llm: LLMClient, console: Console) -> dict:
    console.print("\n[bold]Step 1/9:[/bold] Scraping job posting...")

    job = scrape_job_posting(ctx["job_url"], console=console)
    ctx["job"] = job

    # Create run output directory
    company_safe = _safe_filename(job.get("company") or "unknown")
    ts = date.today().isoformat()
    run_dir = OUTPUT_DIR / f"{company_safe}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    ctx["run_dir"] = str(run_dir)
    ctx["company_safe"] = company_safe

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
        console.print(f"  [yellow]Fit evaluation LLM call failed ({e}). Proceeding without gate.[/yellow]")
        ctx["fit_evaluation"] = None
        ctx["fit_score"] = 50
        ctx["fit_label"] = "UNKNOWN (eval failed)"
        return ctx

    # Parse the response
    evaluation = _parse_fit_evaluation(raw)
    if evaluation is None:
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
        raw_edits = writing_llm.generate(edits_system, edits_user, temperature=0.2)
        ctx["tailor_raw"] = raw_edits
        edits = parse_resume_edits(raw_edits)
        if edits:
            tagline_str = tagline
            edits["tagline"] = edits.get("tagline") or tagline_str
            patched = apply_resume_edits(base_latex, edits)
            # Inject the correct tagline from pipeline config (overrides model output)
            _tagline_repl = "{\\small " + tagline + "}"
            patched = re.sub(
                r"\{\\small [^}]+\}",
                lambda m: _tagline_repl,
                patched, count=1,
            )
            ctx["tailored_latex"] = fix_markdown_lists(patched)
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
            f"  \\href{{https://www.linkedin.com/in/rodecalo/}}{{linkedin.com/in/rodecalo}} \\textbar{{}}\n"
            f"  +4915203590361\n"
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

        raw = writing_llm.generate(
            system_prompt, user_prompt, temperature=0.3,
            content_validator=_is_complete_latex
        )
        ctx["tailor_raw"] = raw

        latex = extract_latex(raw)
        if not latex:
            raise RuntimeError(
                "LLM did not return parseable LaTeX. "
                "Raw response saved to run directory for debugging."
            )

        ctx["tailored_latex"] = fix_markdown_lists(latex)
        console.print(f"  Tailored LaTeX generated: {len(latex)} chars")

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
    try:
        review_raw = writing_llm.generate(review_system, review_user, temperature=0.1)
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

    try:
        review_raw = reviewer.generate(review_system, review_user, temperature=0.2)
        feedback = _parse_review_feedback(review_raw, console)
        ctx["review_feedback"] = feedback

        # Save to run dir for debugging
        run_dir = Path(ctx["run_dir"])
        (run_dir / f"review_feedback_{ctx['company_safe']}.md").write_text(review_raw)

    except Exception as err:
        console.print(f"  [yellow]Reviewer call failed ({err}) — continuing without review.[/yellow]")
        ctx["review_feedback"] = None

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
            latex = latex.replace(old, new, 1)
            applied += 1
            console.print(f"  [green]✓[/green] {reason}")
        else:
            skipped += 1
            console.print(f"  [yellow]⊙[/yellow] old_string not found (skipped): {reason}")

    ctx["tailored_latex"] = latex

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
    """Parse reviewer output into Part A (JSON edits) and Part B (narrative)."""
    import json

    part_a: list[dict] = []
    part_b: list[str] = []

    # Extract Part A: JSON block
    json_match = re.search(r"```(?:json)?\s*\n?(\[[\s\S]*?\])\s*\n?```", raw)
    if json_match:
        try:
            part_a = json.loads(json_match.group(1))
            if not isinstance(part_a, list):
                part_a = []
        except json.JSONDecodeError:
            console.print("  [yellow]Failed to parse Part A JSON — no edits applied.[/yellow]")
            part_a = []

    # Extract Part B: lines starting with SUGGESTION:
    in_part_b = False
    current_suggestion: list[str] = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## Part B") or stripped.startswith("# Part B"):
            in_part_b = True
            if current_suggestion:
                part_b.append("\n".join(current_suggestion))
                current_suggestion = []
            continue
        if stripped.startswith("## Part A") or stripped.startswith("# Part A"):
            in_part_b = False
            continue
        if stripped.startswith("```") and in_part_b:
            continue  # Skip code blocks in Part B
        if in_part_b:
            if stripped.startswith("SUGGESTION:") or stripped.startswith("CONTEXT:") or stripped.startswith("FIX:"):
                current_suggestion.append(stripped)

    if current_suggestion:
        part_b.append("\n".join(current_suggestion))

    return {"part_a": part_a, "part_b": part_b}


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


def step_ats_check(ctx: dict, llm: LLMClient, console: Console) -> dict:
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

    try:
        raw = llm.generate(system_prompt, user_prompt, temperature=0.2)
        ctx["ats_raw"] = raw
        report = parse_ats_report(raw)
    except Exception as e:
        console.print(f"  [yellow]ATS check failed ({e}). Continuing with no ATS edits.[/yellow]")
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

    # Apply edits via LLM (safer than regex on LaTeX)
    writing_llm = create_tailor_client()
    system_prompt = (
        "You are a LaTeX editor. Apply the following edits to the resume. "
        "Output ONLY the complete modified LaTeX between ```latex and ``` markers. "
        "Make exactly the requested changes. Do not change anything else."
    )
    user_prompt = (
        f"## Current LaTeX\n\n{ctx['tailored_latex']}\n\n"
        f"## Edits to Apply\n\n{json.dumps(edits, indent=2)}\n\n"
        f"Apply these edits and return the complete modified LaTeX."
    )

    raw = writing_llm.generate(system_prompt, user_prompt, temperature=0.1)
    updated = extract_latex(raw)

    if updated:
        # Completeness check: catch truncated LLM output before it hits pdflatex.
        # Same check as step 3b — if sections are missing, keep the original.
        _REQUIRED_SECTIONS = [
            (r"\\section\*\{Experience\}", "Experience"),
            (r"\\section\*\{Skills", "Skills & Tools"),
            (r"\\section\*\{Education\}", "Education"),
        ]
        missing = [
            name for pattern, name in _REQUIRED_SECTIONS
            if not re.search(pattern, updated)
        ]
        if missing:
            console.print(
                f"  [red]LLM returned truncated LaTeX after edits "
                f"(missing sections: {', '.join(missing)}). "
                f"Keeping original .tex.[/red]"
            )
        else:
            ctx["tailored_latex"] = fix_markdown_lists(updated)
            Path(ctx["tex_path"]).write_text(ctx["tailored_latex"])
            console.print("  [green]Edits applied. .tex updated.[/green]")
    else:
        console.print(
            "  [red]Failed to parse edited LaTeX. Keeping original.[/red]"
        )

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


# ─── Step 8: Generate Q&A ────────────────────────────────────────


def step_generate_qa(ctx: dict, llm: LLMClient, console: Console) -> dict:
    # Prepend cover letter question if requested
    if ctx.get("generate_cover_letter"):
        # Avoid duplication if user already typed "cover letter" in questions
        all_q = ctx.get("all_questions", [])
        already_has_cl = any(
            "cover letter" in q.lower() for q in all_q
        )
        if not already_has_cl:
            cl_instructions = ctx.get("cover_letter_instructions", "").strip()
            cl_q = "Write a cover letter body for this application. Output ONLY the body paragraphs (2-4 paragraphs). Do NOT include a date line, greeting, sign-off, or any other metadata — only the paragraphs themselves. The LaTeX template supplies the greeting and sign-off."
            if cl_instructions:
                cl_q += f" Additional instructions: {cl_instructions}"
            all_q.insert(0, cl_q)
            ctx["all_questions"] = all_q

    questions = ctx.get("all_questions", [])
    if not questions:
        console.print("\n[bold]Step 8/9:[/bold] No questions — skipping.")
        ctx["qa_answers"] = []
        return ctx

    console.print(
        f"\n[bold]Step 8/9:[/bold] Generating answers for "
        f"{len(questions)} questions..."
    )

    # Company research - use direct URL if provided, otherwise search
    company_url = ctx.get("company_url")
    company_name = ctx["job"].get("company", "")
    company_research = research_company(
        company_name, company_url=company_url, console=console
    )
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
        console.print(f"  Q&A templates loaded")

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
        + (_build_salary_qa_section(ctx.get("salary_benchmark")) if ctx.get("salary_benchmark") else "")
        + f"## Questions to Answer\n\n{questions_text}\n\n"
        f"---\n\n"
        f"{role_framing}\n\n"
        f"Generate answers for each question."
    )

    raw = writing_llm.generate(system_prompt, user_prompt, temperature=0.7)
    ctx["qa_raw"] = raw

    qa_pairs = parse_qa_answers(raw)
    ctx["qa_answers"] = qa_pairs

    # Save Q&A output
    run_dir = Path(ctx["run_dir"])
    (run_dir / f"qa_{ctx['company_safe']}.md").write_text(raw)

    # Save form-data JSON for form_filler
    from config import (
        APPLICANT_NAME,
        APPLICANT_EMAIL,
        APPLICANT_PHONE,
        APPLICANT_LINKEDIN,
        APPLICANT_LOCATION,
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
    if qa_pairs:
        form_data["cover_letter"] = qa_pairs[0]["answer"]

    form_path = run_dir / f"form_data_{ctx['company_safe']}.json"
    form_path.write_text(json.dumps(form_data, indent=2))
    ctx["form_data_path"] = str(form_path)

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
    """
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

    try:
        raw = writing_llm.generate(system_prompt, user_prompt, temperature=0.6)
    except Exception as err:
        console.print(f"  [yellow]Interview prep LLM call failed ({err}) — generating basic template.[/yellow]")
        raw = _fallback_interview_prep(ctx, story_bank)

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


def step_compile_cover_letter(ctx: dict, llm: LLMClient, console: Console) -> dict:
    """If cover letter was requested, extract body from Q&A and compile PDF."""
    if not ctx.get("generate_cover_letter"):
        return ctx

    console.print("\n[bold]Step 9/10:[/bold] Compiling cover letter...")

    qa_answers = ctx.get("qa_answers", [])
    if not qa_answers:
        console.print("  [yellow]No Q&A answers found — skipping.[/yellow]")
        return ctx

    # The first Q&A answer is the cover letter body (prepended question)
    cover_body = qa_answers[0]["answer"].strip()
    if not cover_body or len(cover_body) < 50:
        console.print(f"  [yellow]Cover letter body too short ({len(cover_body)} chars) — skipping.[/yellow]")
        return ctx

    job_title = ctx["job"].get("title", "Unknown")
    company = ctx["job"].get("company", "Unknown")
    run_dir = Path(ctx["run_dir"])

    # Read template
    template_path = PROJECT_ROOT / "templates" / "cover_letter.tex"
    if not template_path.exists():
        console.print(f"  [red]Template not found: {template_path}[/red]")
        return ctx

    today = date.today()
    date_str = today.strftime("%d.%m.%Y")
    from config import APPLICANT_LOCATION
    place = APPLICANT_LOCATION or "Berlin"

    # Fill template (use .replace to avoid LaTeX brace conflicts with .format)
    latex = template_path.read_text()
    latex = latex.replace("{role_title}", job_title)
    latex = latex.replace("{company}", company)
    latex = latex.replace("{place}", place)
    latex = latex.replace("{date}", date_str)

    # Escape LaTeX special characters in body
    import re
    cover_body = re.sub(r"\n?_Used:.*", "", cover_body)  # Strip Q&A tracking line
    cover_body = cover_body.replace("%", "\\%")
    cover_body = cover_body.replace("_", "\\_")
    cover_body = cover_body.replace("&", "\\&")
    cover_body = cover_body.replace("$", "\\$")
    cover_body = cover_body.replace("#", "\\#")
    cover_body = cover_body.replace("~", "\\textasciitilde{}")
    cover_body = cover_body.replace("^", "\\textasciicircum{}")

    # Handle company motivation paragraph (optional — forward-looking framing, Spec 002)
    company_paragraph = ctx.get("cover_letter_company_paragraph", "").strip()
    if company_paragraph:
        company_paragraph = re.sub(r"\n?_Used:.*", "", company_paragraph)
        company_paragraph = company_paragraph.replace("%", "\\%")
        company_paragraph = company_paragraph.replace("_", "\\_")
        company_paragraph = company_paragraph.replace("&", "\\&")
        company_paragraph = company_paragraph.replace("$", "\\$")
        company_paragraph = company_paragraph.replace("#", "\\#")
        company_paragraph = company_paragraph.replace("~", "\\textasciitilde{}")
        company_paragraph = company_paragraph.replace("^", "\\textasciicircum{}")
    latex = latex.replace("{company_paragraph}", company_paragraph)
    latex = latex.replace("{body}", cover_body)

    # Write .tex file
    tex_filename = "Cover-Letter_RodrigoLopes.tex"
    tex_path = run_dir / tex_filename
    tex_path.write_text(latex)
    console.print(f"  [green]Written: {tex_path}[/green]")

    # Compile PDF with inspect-and-fix loop
    result = compile_and_inspect(str(tex_path), doc_type="cover_letter")
    if result.get("ok"):
        ctx["cover_letter_pdf_path"] = result["pdf_path"]
        console.print(f"  [green]PDF: {result['pdf_path']}[/green]")
        if result.get("fixes"):
            console.print(f"  [yellow]Auto-fixes applied: {', '.join(result['fixes'])}[/yellow]")
        if result.get("warning"):
            console.print(f"  [yellow]{result['warning']}[/yellow]")
    else:
        error = result.get("error", "Unknown error")
        console.print(f"  [red]PDF compilation failed: {error}[/red]")
        for line in result.get("details", [])[:3]:
            console.print(f"  [red]{line}[/red]")

    return ctx


# ─── Step 10: Notion Tracking ────────────────────────────────────


def step_create_tracker_entry(
    ctx: dict, llm: LLMClient, console: Console
) -> dict:
    import sys
    from pathlib import Path

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

    entry = {
        "company": company,
        "role": job_title,
        "url": job_url,
        "score": score,
        "score_label": score_label,
        "date": date_str,
        "status": "applied",
        "notes": "",
    }

    apps_file = Path(__file__).parent.parent / "data" / "applications.json"

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
            # Update existing entry with new score/date
            existing[dup_idx].update({
                "score": score,
                "score_label": score_label,
                "date": date_str,
                "status": "applied",
            })
            console.print(f"  [yellow]↻ Updated existing tracker entry (duplicate URL)[/yellow]")
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
