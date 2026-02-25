"""Pipeline step functions for the JobQuest orchestrator.

Each step takes a context dict (ctx), enriches it, and returns it.
Steps call existing scripts via subprocess or new modules directly.
"""

import subprocess
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
from modules.parsers import extract_latex, fix_markdown_lists, parse_ats_report, parse_qa_answers

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
OUTPUT_DIR = PROJECT_ROOT / "output"
VENV_PYTHON = str(PROJECT_ROOT / "venv" / "bin" / "python")
RESUME_CACHE_FILE = PROJECT_ROOT / ".master_resume_cache.txt"
RESUME_CACHE_TTL = 24 * 3600  # 24 hours


def _load_prompt(name: str) -> str:
    """Load a prompt template from prompts/ directory."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


# Module-level writing client cache (created on first use, reused across steps)
_writing_client_cache: LLMClient | None = None


def _get_writing_client() -> LLMClient:
    """Return the cached writing LLM client, creating it on first call."""
    global _writing_client_cache
    if _writing_client_cache is None:
        _writing_client_cache = create_writing_client()
    return _writing_client_cache


def _load_voice_prefix() -> str:
    """Load rodrigo-voice.md as a system prompt prefix for writing steps."""
    voice_path = PROMPTS_DIR / "rodrigo-voice.md"
    if voice_path.exists():
        return voice_path.read_text() + "\n\n---\n\n"
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

    # Use local cache if fresh (avoids Notion API slowness on every run)
    if RESUME_CACHE_FILE.exists():
        age = time.time() - RESUME_CACHE_FILE.stat().st_mtime
        if age < RESUME_CACHE_TTL:
            output = RESUME_CACHE_FILE.read_text()
            if len(output) < 500:
                console.print(f"  [yellow]Cache corrupted ({len(output)} chars), re-fetching...[/yellow]")
                RESUME_CACHE_FILE.unlink()
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
    RESUME_CACHE_FILE.write_text(output)
    ctx["master_resume"] = output
    console.print(f"  Loaded {len(output)} chars")
    return ctx


# ─── Step 3: Tailor Resume via LLM ───────────────────────────────


TAGLINES = {
    "growth_pm": "Experiments that accelerate revenue.",
    "generalist": "End-to-end ownership. Outcomes delivered.",
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
    analysis_user = (
        f"## Job Posting\n\n"
        f"**Title:** {ctx['job']['title']}\n"
        f"**Company:** {ctx['job']['company']}\n\n"
        f"{ctx['job']['description']}\n\n"
        f"---\n\n"
        f"## Candidate Resume\n\n"
        f"{ctx['master_resume']}\n\n"
        f"---\n\n"
        f"Produce the tailoring brief."
    )
    tailoring_brief = llm.generate(analysis_system, analysis_user, temperature=0.2)
    ctx["tailoring_brief"] = tailoring_brief

    # Save brief to run dir for debugging
    run_dir = Path(ctx["run_dir"])
    (run_dir / f"tailoring_brief_{ctx['company_safe']}.md").write_text(tailoring_brief)
    console.print(f"  Tailoring brief: {len(tailoring_brief)} chars")

    # --- Stage 3b: LaTeX generation (writing LLM) ---
    # The writing model receives the pre-built brief as explicit context, so it
    # executes a plan rather than deriving one mid-generation.
    console.print(f"  3b: Generating LaTeX ({writing_llm.model_name()})...")
    system_prompt = _load_voice_prefix() + _load_prompt("resume_tailor")
    # Static/semi-static content first (cached by DeepSeek prefix cache),
    # dynamic content last (changes per application, always after the cached prefix).
    user_prompt = (
        f"## Tailoring Brief\n\n"
        f"This analysis was produced for you in advance. Follow it — it tells you "
        f"which bullets to touch, what the summary strategy is, and what to leave alone.\n\n"
        f"{tailoring_brief}\n\n"
        f"---\n\n"
        f"## Locked Header (copy character-for-character, do not change anything)\n\n"
        f"\\begin{{center}}\n"
        f"  {{\\Huge\\bfseries Rodrigo Lopes,}} {{\\small {tagline}}}\\\\[6pt]\n"
        f"  \\href{{https://rodrigolopes.eu/?utm_source=resume&utm_medium=pdf}}{{rodrigolopes.eu}} \\textbar{{}}\n"
        f"  \\href{{mailto:contact@rodrigolopes.eu}}{{contact@rodrigolopes.eu}} \\textbar{{}}\n"
        f"  \\href{{https://www.linkedin.com/in/rodecalo/}}{{linkedin.com/in/rodecalo}} \\textbar{{}}\n"
        f"  +49 0172 5626057\n"
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
        f"Generate the complete tailored LaTeX resume following the tailoring brief above. "
        f"Output ONLY the LaTeX content between ```latex and ``` markers."
    )

    raw = writing_llm.generate(system_prompt, user_prompt, temperature=0.3)
    ctx["tailor_raw"] = raw

    latex = extract_latex(raw)
    if not latex:
        raise RuntimeError(
            "LLM did not return parseable LaTeX. "
            "Raw response saved to run directory for debugging."
        )
    ctx["tailored_latex"] = fix_markdown_lists(latex)
    console.print(f"  Tailored LaTeX generated: {len(latex)} chars")
    return ctx


# ─── Step 4: Write .tex File ─────────────────────────────────────


def step_write_tex(ctx: dict, llm: LLMClient, console: Console) -> dict:
    console.print("\n[bold]Step 4/9:[/bold] Writing .tex file...")

    run_dir = Path(ctx["run_dir"])
    filename = f"resume_tailored_{ctx['company_safe']}.tex"
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

    raw = llm.generate(system_prompt, user_prompt, temperature=0.2)
    ctx["ats_raw"] = raw

    report = parse_ats_report(raw)
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
            "WFP for AI/research depth. HELLA as secondary."
        ),
        "generalist": (
            "Resume variant: **Generalist PM**. "
            "Foreground full product lifecycle and stakeholder management: FORVIA HELLA "
            "(B2B platform, roadmap, cross-functional delivery, €12M revenue). "
            "Accenture and C&A as supporting evidence of execution breadth."
        ),
    }.get(ROLE_VARIANT, "")

    writing_llm = _get_writing_client()
    system_prompt = _load_voice_prefix() + _load_prompt("qa_generator")
    questions_text = "\n".join(
        f"{i + 1}. {q.strip()}" for i, q in enumerate(questions)
    )
    # Static/semi-static content first (cached by DeepSeek prefix cache),
    # dynamic content last (changes per application, always after the cached prefix).
    user_prompt = (
        f"## Master Resume\n\n{ctx['master_resume']}\n\n"
        f"---\n\n"
        f"{templates_section}"
        f"---\n\n"
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

    raw = writing_llm.generate(system_prompt, user_prompt, temperature=0.5)
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


# ─── Step 9: Notion Tracking ─────────────────────────────────────


def step_create_notion_entry(
    ctx: dict, llm: LLMClient, console: Console
) -> dict:
    import sys

    if ctx.get("skip_notion"):
        console.print("\n[bold]Step 9/9:[/bold] Skipping Notion (--skip-notion).")
        return ctx

    console.print("\n[bold]Step 9/9:[/bold] Creating Notion entry...")
    sys.stdout.flush()

    qa_text = ""
    for qa in ctx.get("qa_answers", []):
        qa_text += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"

    from config import RESUME_VARIANT

    job_title = ctx["job"].get("title") or "Unknown"
    company = ctx["job"].get("company") or "Unknown"
    job_url = ctx["job_url"]

    console.print(f"  Job: {job_title} at {company}")
    sys.stdout.flush()

    args = [
        "create",
        "--title", job_title,
        "--company", company,
        "--url", job_url,
    ]
    if qa_text:
        args += ["--qa", qa_text[:4000]]
    if RESUME_VARIANT:
        args += ["--variant", RESUME_VARIANT]

    try:
        output = _run_script("notion_tracker.py", args)
        result = json.loads(output)
        if result.get("success"):
            ctx["notion_page_id"] = result.get("page_id")
            console.print(f"  [green]✓ Created Notion entry: {result.get('url', '')}[/green]")
        else:
            console.print(f"  [red]✗ Notion failed: {result}[/red]")
    except json.JSONDecodeError as e:
        console.print(f"  [red]✗ Notion JSON parse error: {e}[/red]")
        console.print(f"  [red]  Raw output: {output[:200]}[/red]")
    except Exception as e:
        console.print(f"  [red]✗ Notion error: {type(e).__name__}: {e}[/red]")
        console.print("  Continuing without Notion entry.")

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
