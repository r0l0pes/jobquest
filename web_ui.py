#!/usr/bin/env python3
"""JobQuest Browser UI - Gradio-based interface for job applications."""

import subprocess
import json
import os
from pathlib import Path
from datetime import datetime

import gradio as gr

PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON = str(PROJECT_ROOT / "venv" / "bin" / "python")
OUTPUT_DIR = PROJECT_ROOT / "output"
STATS_FILE = PROJECT_ROOT / ".usage_stats.json"


def load_stats():
    """Load usage stats from file."""
    default = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "providers": {
            "gemini": {"calls": 0, "apps": 0},
            "groq": {"calls": 0, "apps": 0},
            "sambanova": {"calls": 0, "apps": 0},
        }
    }
    if STATS_FILE.exists():
        try:
            data = json.loads(STATS_FILE.read_text())
            if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
                return default
            if "providers" not in data:
                data["providers"] = default["providers"]
            for p in default["providers"]:
                if p not in data["providers"]:
                    data["providers"][p] = {"calls": 0, "apps": 0}
            return data
        except:
            pass
    return default


def save_stats(stats):
    """Save usage stats to file."""
    STATS_FILE.write_text(json.dumps(stats, indent=2))


def get_stats_display():
    """Get formatted stats for display."""
    stats = load_stats()

    limits = {
        "gemini": {"calls": 100, "label": "Gemini"},
        "groq": {"calls": 1000, "label": "Groq"},
        "sambanova": {"calls": 500, "label": "SambaNova"},
    }

    lines = []
    for provider, info in limits.items():
        p_stats = stats["providers"].get(provider, {"calls": 0, "apps": 0})
        calls = p_stats.get("calls", 0)
        apps = p_stats.get("apps", 0)
        remaining = max(0, info["calls"] - calls)
        pct = (calls / info["calls"]) * 100

        status = "🟢" if pct < 80 else "🟡" if pct < 100 else "🔴"
        lines.append(f"{status} **{info['label']}**: {calls}/{info['calls']} ({apps} apps)")

    return " | ".join(lines)


def get_recent_outputs():
    """Get list of recent output directories."""
    if not OUTPUT_DIR.exists():
        return "No outputs yet."

    dirs = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir()], reverse=True)[:8]
    if not dirs:
        return "No outputs yet."

    lines = []
    for d in dirs:
        pdf = list(d.glob("*.pdf"))
        status = "✅" if pdf else "⏳"
        lines.append(f"{status} {d.name}")

    return " | ".join(lines)


def run_application(job_url, company_url, questions, provider):
    """Run the application pipeline."""
    if not job_url or not job_url.strip():
        yield "❌ Please enter a job URL"
        return

    cmd = [VENV_PYTHON, "apply.py", job_url.strip()]

    if company_url and company_url.strip():
        cmd.extend(["--company-url", company_url.strip()])

    if questions and questions.strip():
        for q in questions.strip().split("\n"):
            if q.strip():
                cmd.extend(["--questions", q.strip()])

    full_env = os.environ.copy()
    full_env["LLM_PROVIDER"] = provider
    full_env["PYTHONUNBUFFERED"] = "1"  # Ensure real-time output

    yield f"🚀 Starting with {provider}...\n\n"

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line buffering
        cwd=str(PROJECT_ROOT),
        env=full_env,
    )

    output_lines = []
    providers_used = set()

    for line in iter(process.stdout.readline, ''):
        output_lines.append(line)
        if "exhausted, trying next" in line.lower():
            for p in ["gemini", "groq", "sambanova"]:
                if p in line.lower():
                    providers_used.add(p)
        yield "".join(output_lines)

    process.wait()

    # Update stats
    stats = load_stats()
    if provider not in stats["providers"]:
        stats["providers"][provider] = {"calls": 0, "apps": 0}

    if process.returncode == 0:
        calls_per_provider = 4 // max(1, len(providers_used) + 1)
        stats["providers"][provider]["calls"] += calls_per_provider
        stats["providers"][provider]["apps"] += 1
        for p in providers_used:
            if p != provider:
                if p not in stats["providers"]:
                    stats["providers"][p] = {"calls": 0, "apps": 0}
                stats["providers"][p]["calls"] += calls_per_provider
    else:
        stats["providers"][provider]["calls"] += 2

    save_stats(stats)

    if process.returncode == 0:
        output_lines.append("\n\n✅ **Complete!**")
    else:
        output_lines.append("\n\n❌ **Failed** - check output above")

    yield "".join(output_lines)


def create_app_form(slot_num):
    """Create a single application form."""
    with gr.Column():
        job_url = gr.Textbox(
            label="Job URL",
            placeholder="https://jobs.lever.co/company/...",
            lines=1,
        )
        company_url = gr.Textbox(
            label="Company URL (optional)",
            placeholder="https://company.com",
            lines=1,
        )
        questions = gr.Textbox(
            label="Questions (one per line)",
            placeholder="Why this role?\nCover letter",
            lines=4,
        )
        provider = gr.Radio(
            choices=["gemini", "groq", "sambanova"],
            value="gemini",
            label="Provider",
        )
        submit_btn = gr.Button(f"🚀 Run #{slot_num}", variant="primary")
        output = gr.Textbox(
            label="Output",
            lines=15,
            max_lines=30,
            interactive=False,
        )

    return job_url, company_url, questions, provider, submit_btn, output


def create_ui():
    """Create the Gradio interface with 3 parallel forms."""
    with gr.Blocks(title="JobQuest") as app:
        gr.Markdown("# 🎯 JobQuest — Parallel Applications")

        # Stats bar
        with gr.Row():
            stats_display = gr.Markdown(get_stats_display())
            refresh_btn = gr.Button("🔄", size="sm", scale=0)

        # Recent outputs
        recent_display = gr.Markdown(get_recent_outputs())

        gr.Markdown("---")

        # 3 parallel application forms
        with gr.Row():
            with gr.Column():
                gr.Markdown("### Application 1")
                j1, c1, q1, p1, b1, o1 = create_app_form(1)

            with gr.Column():
                gr.Markdown("### Application 2")
                j2, c2, q2, p2, b2, o2 = create_app_form(2)

            with gr.Column():
                gr.Markdown("### Application 3")
                j3, c3, q3, p3, b3, o3 = create_app_form(3)

        # Event handlers - each form runs independently (concurrency_limit=None means no limit)
        b1.click(fn=run_application, inputs=[j1, c1, q1, p1], outputs=o1, concurrency_limit=None)
        b2.click(fn=run_application, inputs=[j2, c2, q2, p2], outputs=o2, concurrency_limit=None)
        b3.click(fn=run_application, inputs=[j3, c3, q3, p3], outputs=o3, concurrency_limit=None)

        refresh_btn.click(
            fn=lambda: (get_stats_display(), get_recent_outputs()),
            outputs=[stats_display, recent_display],
        )

    return app


if __name__ == "__main__":
    app = create_ui()
    # Enable queue with no concurrency limit (allows parallel execution)
    app.queue(default_concurrency_limit=None)
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=True,
        theme=gr.themes.Soft(),
    )
