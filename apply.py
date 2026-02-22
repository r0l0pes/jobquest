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
        choices=["gemini", "groq", "sambanova"],
        help="LLM provider (default: from LLM_PROVIDER env or gemini)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show pipeline plan without executing",
    )
    return parser.parse_args(argv)





def build_steps():
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
        step_create_notion_entry,
    )
    
    return [
        ("scrape", "Scrape job posting", step_scrape_job),
        ("resume", "Read master resume from Notion", step_read_master_resume),
        ("tailor", "Tailor resume via LLM", step_tailor_resume),
        ("write_tex", "Write .tex file", step_write_tex),
        ("ats_check", "Run ATS keyword check", step_ats_check),
        ("ats_apply", "Review & apply ATS edits", step_apply_ats_edits),
        ("compile", "Compile PDF", step_compile_pdf),
        ("qa", "Generate Q&A answers", step_generate_qa),
        ("notion", "Create Notion entry", step_create_notion_entry),
    ]


def execute_step(step_id, desc, step_fn, ctx, llm, console):
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
        elif step_id == "qa" and not ctx.get("questions"):
            skip = "[dim]no questions[/dim]"
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

    table.add_row("Output Dir", ctx.get("run_dir", "?"))

    console.print()
    console.print(table)


def run_pipeline_from_cli(args) -> int:
    """Execute pipeline from CLI arguments."""
    from modules.llm_client import create_client
    
    console = Console()
    
    STEPS = build_steps()
    
    # Resolve provider: CLI arg > env var > default
    provider = args.provider or os.getenv("LLM_PROVIDER", "gemini")

    # Build initial context
    ctx = {
        "job_url": args.job_url,
        "company_url": args.company_url,
        "questions": [q.strip() for q in args.questions if q.strip()],
        "skip_notion": args.skip_notion,
        "provider": provider,
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
            ctx = execute_step(step_id, desc, step_fn, ctx, llm, console)
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


if __name__ == "__main__":
    main()
