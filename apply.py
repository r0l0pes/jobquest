#!/usr/bin/env python3
"""JobQuest Pipeline Orchestrator.

Usage:
    python apply.py <job_url>
    python apply.py <job_url> --questions "Why this role?;Tell us about yourself"
    python apply.py <job_url> --dry-run
"""

import argparse
import os
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

from rich.console import Console
from rich.panel import Panel
from rich.table import Table




def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="JobQuest — Automated job application pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python apply.py https://boards.greenhouse.io/company/jobs/123\n"
            '  python apply.py https://jobs.lever.co/company/abc --questions "Why us?"\n'
            "  python apply.py https://example.com/jobs/pm --skip-notion\n"
        ),
    )
    parser.add_argument("job_url", help="URL of the job posting")
    parser.add_argument(
        "--company-url",
        help="Company website URL for research (e.g., https://company.com)",
    )
    parser.add_argument(
        "--questions",
        action="append",
        default=[],
        help="Application question (use multiple times for multiple questions)",
    )
    parser.add_argument(
        "--skip-notion",
        action="store_true",
        help="Skip Notion tracking step",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini", "groq", "sambanova", "openrouter"],
        help="LLM provider for ATS and free-tier steps (default: from LLM_PROVIDER env or gemini)",
    )
    parser.add_argument(
        "--writing-model",
        choices=[
            "gemini-2.5-pro", "gemini-3.1-flash-lite",
            "llama-3.3-70b", "llama-3.1-405b",
            "qwen3.5-397b-a17b",
            "kimi-k2.6", "deepseek-chat",
        ],
        help="Writing model for steps 3, 6, 8 (default: gemini-2.5-pro)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show pipeline plan without executing",
    )
    parser.add_argument(
        "--fill-form",
        action="store_true",
        help="Open browser form filler after PDF generation (reviews fields, never auto-submits)",
    )
    parser.add_argument(
        "--skip-form",
        action="store_true",
        help="Skip form filler step (default behavior; use --fill-form to enable)",
    )
    parser.add_argument(
        "--cover-letter",
        action="store_true",
        help="Generate a cover letter in LaTeX + PDF from LLM-generated body",
    )
    parser.add_argument(
        "--cover-letter-instructions",
        help="Optional specific instructions for the cover letter (e.g., 'Emphasize AI experience')",
    )
    return parser.parse_args(argv)





def build_steps(fill_form: bool = False):
    """Build the pipeline steps list with lazy imports."""
    from modules.pipeline import (
        step_scrape_job,
        step_read_master_resume,
        step_tailor_resume,
        step_write_tex,
        step_ats_check,
        step_apply_ats_edits,
        step_compile_pdf,
        step_generate_qa,
        step_compile_cover_letter,
        step_create_tracker_entry,
        step_run_form_filler,
        compute_pipeline_score,
    )

    def _step_score(ctx, llm, console):
        """Thin wrapper: compute_pipeline_score matches the step signature."""
        console.print("\n[bold]Step 9/10:[/bold] Computing pipeline score...")
        compute_pipeline_score(ctx, console)
        return ctx
    
    steps = [
        ("scrape", "Scrape job posting", step_scrape_job),
        ("resume", "Read master resume from Notion", step_read_master_resume),
        ("tailor", "Tailor resume via LLM", step_tailor_resume),
        ("write_tex", "Write .tex file", step_write_tex),
        ("ats_check", "Run ATS keyword check", step_ats_check),
        ("ats_apply", "Review & apply ATS edits", step_apply_ats_edits),
        ("compile", "Compile PDF", step_compile_pdf),
        ("qa", "Generate Q&A answers", step_generate_qa),
        ("cl", "Compile cover letter", step_compile_cover_letter),
        ("score", "Compute pipeline score", _step_score),
        ("tracker", "Create tracker entry", step_create_tracker_entry),
    ]

    if fill_form:
        steps.append(("form", "Open form filler", step_run_form_filler))

    return steps


def execute_step(step_fn, ctx, llm, console):
    return step_fn(ctx=ctx, llm=llm, console=console)


def show_dry_run(ctx: dict, console: Console, steps):
    """Print planned steps without executing."""
    table = Table(title="Pipeline Steps (dry run)")
    table.add_column("Step", style="bold")
    table.add_column("Action")
    table.add_column("Status")

    for i, (step_id, desc, _) in enumerate(steps, 1):
        skip = ""
        if step_id == "notion" and ctx.get("skip_notion"):
            skip = "[yellow]SKIP[/yellow]"
        elif step_id == "form" and ctx.get("skip_form"):
            skip = "[yellow]SKIP[/yellow]"
        else:
            skip = "[green]RUN[/green]"
        table.add_row(f"{i}", desc, skip)

    console.print(table)
    console.print(f"\nJob URL: {ctx['job_url']}")
    console.print(f"Provider: {ctx.get('provider', 'gemini')} (cross-provider fallback enabled)")
    if ctx.get("questions"):
        console.print(f"Questions: {len(ctx['questions'])}")


def show_summary(ctx: dict, console: Console):
    """Print final summary after pipeline completes."""
    table = Table(title="Application Summary")
    table.add_column("Item", style="bold")
    table.add_column("Value")

    table.add_row("Company", ctx.get("job", {}).get("company", "?"))
    table.add_row("Job Title", ctx.get("job", {}).get("title", "?"))
    table.add_row("Source", ctx.get("job", {}).get("source", "?"))

    if ctx.get("tex_path"):
        table.add_row("LaTeX", ctx["tex_path"])
    if ctx.get("pdf_path"):
        table.add_row("PDF", ctx["pdf_path"])

    ats = (ctx.get("ats_report", {}).get("json") or {}).get(
        "coverage_score", {}
    )
    if ats:
        table.add_row(
            "ATS Coverage",
            f"{ats.get('coverage_pct', '?')}% — {ats.get('verdict', '?')}",
        )

    qa_count = len(ctx.get("qa_answers", []))
    if qa_count:
        table.add_row("Q&A Answers", str(qa_count))

    if ctx.get("notion_page_id"):
        table.add_row("Notion Entry", ctx["notion_page_id"])

    score = ctx.get("pipeline_score")
    if score is not None:
        label = ctx.get("pipeline_score_label", "?")
        style = {"STRONG": "green", "GOOD": "yellow", "WEAK": "yellow", "SKIP": "red"}.get(label, "")
        table.add_row("Pipeline Score", f"[{style}]{score}/100 — {label}[/{style}]")

    table.add_row("Output Dir", ctx.get("run_dir", "?"))

    console.print()
    console.print(table)


def run_pipeline_from_cli(args) -> int:
    """Execute pipeline from CLI arguments."""
    from dotenv import load_dotenv
    from modules.llm_client import create_client
    
    load_dotenv()
    
    console = Console()
    
    fill_form = getattr(args, 'fill_form', False) and not getattr(args, 'skip_form', False)
    STEPS = build_steps(fill_form=fill_form)
    
    # Resolve provider: CLI arg > env var > default
    provider = args.provider or os.getenv("LLM_PROVIDER", "gemini")

    # Resolve writing model: CLI arg > env var > default
    _WRITING_MODEL_TO_PROVIDER = {
        "gemini-2.5-pro": "gemini",
        "gemini-3.1-flash-lite": "gemini",
        "llama-3.3-70b": "groq",
        "llama-3.1-405b": "sambanova",
        "qwen3.5-397b-a17b": "openrouter",
        "kimi-k2.6": "opencode",
        "deepseek-chat": "deepseek",
    }
    writing_model = getattr(args, 'writing_model', None)
    if writing_model:
        os.environ["GEMINI_WRITING_MODEL"] = writing_model
        os.environ["WRITING_PROVIDER"] = _WRITING_MODEL_TO_PROVIDER.get(writing_model, "gemini")

    # Build initial context
    ctx = {
        "job_url": args.job_url,
        "company_url": args.company_url,
        "questions": [q.strip() for q in args.questions if q.strip()],
        "skip_notion": args.skip_notion,
        "skip_form": not fill_form,
        "provider": provider,
        "generate_cover_letter": args.cover_letter,
        "cover_letter_instructions": args.cover_letter_instructions or "",
    }

    # Dry run
    if args.dry_run:
        console.print(
            Panel(
                "[bold]DRY RUN[/bold] — showing planned steps, not executing.",
                style="yellow",
            )
        )
        show_dry_run(ctx, console, STEPS)
        return 0

    # Banner
    console.print(
        Panel(
            f"[bold]JobQuest Pipeline[/bold]\n"
            f"URL: {args.job_url}\n"
            f"Provider: {provider} (cross-provider fallback enabled)",
            style="blue",
        )
    )

    # Initialize LLM with cross-provider fallback
    try:
        llm = create_client(provider=provider, fallback=True)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return 1

    # Run pipeline
    for i, (step_id, desc, step_fn) in enumerate(STEPS, 1):
        try:
            new_ctx = execute_step(step_fn, ctx, llm, console)
            ctx = new_ctx
        except KeyboardInterrupt:
            console.print("\n[yellow]Pipeline interrupted by user.[/yellow]")
            # Save what we have
            _save_context(ctx, console)
            return 0
        except Exception as e:
            console.print(f"\n[red]Step {i} ({desc}) failed: {e}[/red]")
            _save_context(ctx, console)
            return 1

    # Done - save context and show summary
    _save_context(ctx, console)
    _save_application_json(ctx, console)
    console.print(
        Panel("[bold green]Pipeline complete.[/bold green]", style="green")
    )
    show_summary(ctx, console)
    return 0


def main():
    args = parse_args()
    return_code = run_pipeline_from_cli(args)
    sys.exit(return_code)


def _save_context(ctx: dict, console: Console):
    """Save pipeline context for debugging."""
    run_dir = ctx.get("run_dir")
    if not run_dir:
        return
    try:
        # Save serializable parts of context
        safe_ctx = {}
        for k, v in ctx.items():
            if isinstance(v, (str, int, float, bool, list, dict, type(None))):
                safe_ctx[k] = v
        path = Path(run_dir) / "pipeline_context.json"
        path.write_text(json.dumps(safe_ctx, indent=2, default=str))
        console.print(f"  [dim]Context saved: {path}[/dim]")
    except Exception:
        pass


def _save_application_json(ctx: dict, console: Console):
    """Save or update application in data/applications.json for the tracker.
    Replaces existing entry by URL to avoid duplicates."""
    try:
        data_dir = PROJECT_ROOT / "data"
        data_dir.mkdir(exist_ok=True)
        app_file = data_dir / "applications.json"

        apps = []
        if app_file.exists():
            apps = json.loads(app_file.read_text())

        from datetime import datetime
        from pathlib import Path

        run_dir = ctx.get("run_dir", "")
        company_safe = ctx.get("company_safe", "")

        # Load Q&A from output file if it exists
        qa = ""
        if run_dir and company_safe:
            qa_path = Path(run_dir) / f"qa_{company_safe}.md"
            if qa_path.exists():
                qa = qa_path.read_text()

        # Find cover letter file (.tex preferred, .pdf fallback)
        cover_letter = ""
        cover_letter_content = ""
        if run_dir:
            cl_dir = Path(run_dir)
            cl_tex = list(cl_dir.glob("Cover-Letter*.tex"))
            cl_pdf = list(cl_dir.glob("Cover-Letter*.pdf"))
            if cl_tex:
                cover_letter = str(cl_tex[0])
                cover_letter_content = cl_tex[0].read_text()
            elif cl_pdf:
                cover_letter = str(cl_pdf[0])

        # Find resume file (.tex preferred, .pdf fallback)
        resume = ""
        resume_content = ""
        if run_dir:
            res_dir = Path(run_dir)
            res_tex = list(res_dir.glob("Resume_*.tex"))
            res_pdf = list(res_dir.glob("Resume_*.pdf"))
            if res_tex:
                resume = str(res_tex[0])
                resume_content = res_tex[0].read_text()
            elif res_pdf:
                resume = str(res_pdf[0])

        app = {
            "company": ctx.get("job", {}).get("company", "?"),
            "role": ctx.get("job", {}).get("title", "?"),
            "url": ctx.get("job_url", ""),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "score": ctx.get("pipeline_score"),
            "score_label": ctx.get("pipeline_score_label"),
            "status": "applied",
            "notes": "",
            "pdf_path": ctx.get("pdf_path", ""),
            "run_dir": run_dir,
            "qa": qa,
            "cover_letter": cover_letter,
            "cover_letter_content": cover_letter_content,
            "resume": resume,
            "resume_content": resume_content,
        }

        # Replace existing entry by URL (dedup on save)
        url = app["url"]
        replaced = False
        for i, existing in enumerate(apps):
            if existing.get("url", "") == url:
                apps[i] = app
                replaced = True
                console.print(f"  [dim]Updated existing tracker entry for {app['company']}[/dim]")
                break

        if not replaced:
            apps.append(app)

        app_file.write_text(json.dumps(apps, indent=2))
        console.print(f"  [dim]Tracker updated: {app_file} ({len(apps)} entries)[/dim]")
    except Exception as e:
        console.print(f"  [red]Tracker save error: {e}[/red]")


if __name__ == "__main__":
    main()
