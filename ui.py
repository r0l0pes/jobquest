#!/usr/bin/env python3
"""JobQuest Interactive UI - Terminal-based interface for job applications."""

import subprocess
import sys
import os
import json
from pathlib import Path
from datetime import datetime
import threading
import time

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.text import Text

console = Console()

PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON = str(PROJECT_ROOT / "venv" / "bin" / "python")
OUTPUT_DIR = PROJECT_ROOT / "output"
STATS_FILE = PROJECT_ROOT / ".usage_stats.json"


def load_stats():
    """Load usage stats from file."""
    if STATS_FILE.exists():
        try:
            data = json.loads(STATS_FILE.read_text())
            # Reset if new day
            if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
                return {"date": datetime.now().strftime("%Y-%m-%d"), "calls": 0, "apps": 0}
            return data
        except:
            pass
    return {"date": datetime.now().strftime("%Y-%m-%d"), "calls": 0, "apps": 0}


def save_stats(stats):
    """Save usage stats to file."""
    STATS_FILE.write_text(json.dumps(stats))


def show_stats():
    """Display usage statistics."""
    stats = load_stats()

    table = Table(title="📊 Today's Usage", show_header=False, box=None)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    calls = stats.get("calls", 0)
    apps = stats.get("apps", 0)
    max_calls = 100  # 5 models × 20/day
    remaining_apps = (max_calls - calls) // 4

    table.add_row("API Calls", f"{calls} / {max_calls}")
    table.add_row("Applications", str(apps))
    table.add_row("Remaining Capacity", f"~{remaining_apps} apps")

    console.print(table)

    if calls > 80:
        console.print("[yellow]⚠️  Running low on daily quota![/yellow]")

    console.print()


def show_guidelines():
    """Show usage guidelines."""
    console.print(Panel(
        "[bold]Guidelines[/bold]\n\n"
        "• Run 2-3 applications at a time max\n"
        "• Wait ~30s between starting each\n"
        "• ~25 applications/day on free tier\n"
        "• Each application takes ~4 API calls\n"
        "• Runtime: 2-5 minutes per application\n\n"
        "[bold]Questions[/bold]\n"
        "• Yes/No questions → Always answer 'Yes'\n"
        "• Cover letters → 250-350 words, be specific",
        title="📋 Quick Reference",
        border_style="blue"
    ))


def get_application_input():
    """Get application details from user."""
    console.print("\n[bold cyan]═══ New Application ═══[/bold cyan]\n")

    job_url = Prompt.ask("Job posting URL")
    if not job_url:
        return None

    company_url = Prompt.ask("Company website URL (for research)", default="")

    console.print("\nEnter application questions (one per line, empty line to finish):")
    questions = []
    while True:
        q = Prompt.ask("  Question", default="")
        if not q:
            break
        questions.append(q)

    return {
        "job_url": job_url,
        "company_url": company_url,
        "questions": questions,
    }


def run_application(job_url: str, company_url: str = "", questions: list = None):
    """Run the application pipeline."""
    questions = questions or []

    cmd = [VENV_PYTHON, "apply.py", job_url]

    if company_url:
        cmd.extend(["--company-url", company_url])

    for q in questions:
        if q.strip():
            cmd.extend(["--questions", q.strip()])

    console.print(f"\n[dim]Running: {' '.join(cmd[:3])}...[/dim]\n")

    # Run process
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    # Stream output
    for line in iter(process.stdout.readline, ''):
        console.print(line.rstrip())

    process.wait()

    # Update stats
    stats = load_stats()
    stats["calls"] = stats.get("calls", 0) + 4
    stats["apps"] = stats.get("apps", 0) + 1
    save_stats(stats)

    return process.returncode == 0


def show_recent_outputs():
    """Show recent output directories."""
    if not OUTPUT_DIR.exists():
        return

    dirs = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir()], reverse=True)[:5]

    if dirs:
        console.print("\n[bold]📁 Recent Outputs[/bold]")
        for d in dirs:
            pdf = list(d.glob("*.pdf"))
            status = "✅" if pdf else "📝"
            console.print(f"  {status} {d.name}")
        console.print()


def main_menu():
    """Show main menu and handle selection."""
    console.clear()
    console.print(Panel(
        "[bold]🎯 JobQuest[/bold]\n"
        "Automated Job Application Pipeline",
        style="blue"
    ))

    show_stats()

    console.print("[bold]Options:[/bold]")
    console.print("  [1] Run new application")
    console.print("  [2] View guidelines")
    console.print("  [3] View recent outputs")
    console.print("  [q] Quit")
    console.print()

    choice = Prompt.ask("Select", choices=["1", "2", "3", "q"], default="1")

    if choice == "1":
        app = get_application_input()
        if app:
            success = run_application(
                app["job_url"],
                app["company_url"],
                app["questions"]
            )
            if success:
                console.print("\n[green]✅ Application complete![/green]")
            else:
                console.print("\n[red]❌ Application failed[/red]")

            Prompt.ask("\nPress Enter to continue")

    elif choice == "2":
        show_guidelines()
        Prompt.ask("\nPress Enter to continue")

    elif choice == "3":
        show_recent_outputs()
        Prompt.ask("\nPress Enter to continue")

    elif choice == "q":
        console.print("\n[dim]Goodbye![/dim]")
        return False

    return True


def main():
    """Main entry point."""
    try:
        while main_menu():
            pass
    except KeyboardInterrupt:
        console.print("\n\n[dim]Interrupted. Goodbye![/dim]")


if __name__ == "__main__":
    main()
