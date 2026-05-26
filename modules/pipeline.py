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

from modules.llm_client import LLMClient, create_writing_client
from modules.job_scraper import scrape_job_posting, research_company
from modules.parsers import extract_latex, fix_markdown_lists, parse_ats_report, parse_qa_answers, parse_resume_edits, apply_resume_edits

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
    """Return the cached writing LLM client, creating it on first call.

    Uses the user's selected model (WRITING_PROVIDER / GEMINI_WRITING_MODEL env vars)
    with automatic free-first fallback across Gemini → OpenCode → OpenRouter → Groq → SambaNova.
    """
    cache_key = "_singleton"
    if cache_key not in _writing_client_cache:
        _writing_client_cache[cache_key] = create_writing_client()
    return _writing_client_cache[cache_key]


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


# ─── Step 3: Tailor Resume via LLM ───────────────────────────────


TAGLINES = {
    "growth_pm": "Experiments that accelerate revenue.",
    "generalist": "End-to-end ownership. Outcomes delivered.",
    "ai_pm": "AI products, from 0 to 1.",
}


def step_tailor_resume(ctx: dict, llm: LLMClient, console: Console) -> dict:
    writing_llm = _get_writing_client()
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

    targeted_mode = os.getenv("TARGETED_EDITS", "0") == "1"

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
    writing_llm = _get_writing_client()
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

    output = _run_script("render_pdf.py", [ctx["tex_path"]])
    result = json.loads(output)

    if not result.get("success"):
        error = result.get("error", "Unknown error")
        for line in result.get("details", [])[:5]:
            console.print(f"  [red]{line}[/red]")
        raise RuntimeError(f"PDF compilation failed: {error}")

    ctx["pdf_path"] = result["pdf_path"]
    console.print(f"  [green]PDF: {result['pdf_path']}[/green]")
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

    writing_llm = _get_writing_client()
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

    # Static/semi-static content first (cached by DeepSeek prefix cache),
    # dynamic content last (changes per application, always after the cached prefix).
    user_prompt = (
        f"## Master Resume\n\n{ctx['master_resume']}\n\n"
        f"---\n\n"
        f"{templates_section}"
        f"---\n\n"
        f"{qa_ai_context_section}"
        f"## Job Posting\n\n"
        f"**Title:** {ctx['job']['title']}\n"
        f"**Company:** {ctx['job']['company']}\n\n"
        f"{ctx['job']['description'][:3000]}\n\n"
        f"---\n\n"
        f"## Company Research\n\n{company_research[:2000]}\n\n"
        f"---\n\n"
        f"## Questions to Answer\n\n{questions_text}\n\n"
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

    latex = latex.replace("{body}", cover_body)

    # Write .tex file
    tex_filename = "Cover-Letter_RodrigoLopes.tex"
    tex_path = run_dir / tex_filename
    tex_path.write_text(latex)
    console.print(f"  [green]Written: {tex_path}[/green]")

    # Compile PDF (reuse render_pdf.py as subprocess)
    output = _run_script("render_pdf.py", [str(tex_path)])
    result = json.loads(output)
    if result.get("success"):
        ctx["cover_letter_pdf_path"] = result["pdf_path"]
        console.print(f"  [green]PDF: {result['pdf_path']}[/green]")
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
