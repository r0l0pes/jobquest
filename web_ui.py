#!/usr/bin/env python3
"""JobQuest Browser UI - Gradio-based interface for job applications."""

import subprocess
import signal
import json
import os
from pathlib import Path
from datetime import datetime
from threading import Lock

import gradio as gr

PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON = str(PROJECT_ROOT / "venv" / "bin" / "python")
OUTPUT_DIR = PROJECT_ROOT / "output"
STATS_FILE = PROJECT_ROOT / ".usage_stats.json"

RESUME_VARIANTS = {
    "Growth PM": "2f40fd98-227b-8083-a78f-c61c38e55a12",
    "Generalist": "30b0fd98-227b-8195-9649-fe5287cb8cb9",
}

# Store running processes for each slot
running_processes = {1: None, 2: None, 3: None}
process_lock = Lock()


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

    ats_parts = []
    for provider, info in limits.items():
        p_stats = stats["providers"].get(provider, {"calls": 0, "apps": 0})
        calls = p_stats.get("calls", 0)
        apps = p_stats.get("apps", 0)
        pct = (calls / info["calls"]) * 100

        status = "🟢" if pct < 80 else "🟡" if pct < 100 else "🔴"
        ats_parts.append(f"{status} {info['label']}: {calls}/{info['calls']} ({apps} apps)")

    return "**ATS step (5):** " + " | ".join(ats_parts) + " — **Writing steps (3,6,8):** DeepSeek → OpenRouter → Haiku"


def get_recent_outputs():
    """Get list of recent output directories."""
    if not OUTPUT_DIR.exists():
        return "No outputs yet."

    dirs = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir()], reverse=True)[:8]
    if not dirs:
        return "No outputs yet."

    complete = sum(1 for d in dirs if list(d.glob("*.pdf")))
    pending = len(dirs) - complete

    return f"Recent: {complete} complete, {pending} pending"


def stop_process(slot_num):
    """Stop a running process for the given slot."""
    global running_processes
    with process_lock:
        process = running_processes.get(slot_num)
        if process and process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                return "⏹️ Process stopped"
            except Exception:
                try:
                    process.terminate()
                    return "⏹️ Process terminated"
                except:
                    pass
        return "No process to stop"


def _run_pipeline(job_url, company_url, questions, provider, resume_variant, slot_num):
    """Internal generator for running the pipeline."""
    global running_processes

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
    full_env["PYTHONUNBUFFERED"] = "1"

    # Override master resume ID and set role variant for the subprocess
    variant_label = resume_variant or "Growth PM"
    resume_id = RESUME_VARIANTS.get(variant_label, RESUME_VARIANTS["Growth PM"])
    full_env["NOTION_MASTER_RESUME_ID"] = resume_id
    full_env["ROLE_VARIANT"] = variant_label.lower().replace(" ", "_")

    yield f"🚀 Starting with {provider} · {variant_label} resume...\n\n"

    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(PROJECT_ROOT),
            env=full_env,
            preexec_fn=os.setsid,
        )
    except Exception as e:
        yield f"❌ Failed to start: {e}"
        return

    with process_lock:
        running_processes[slot_num] = process

    output_lines = []
    providers_used = set()

    try:
        for line in iter(process.stdout.readline, ''):
            output_lines.append(line)
            if "exhausted, trying next" in line.lower():
                for p in ["gemini", "groq", "sambanova"]:
                    if p in line.lower():
                        providers_used.add(p)
            yield "".join(output_lines)

        process.wait()
    finally:
        with process_lock:
            running_processes[slot_num] = None

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
    elif process.returncode in (-15, -9):
        output_lines.append("\n\n⏹️ **Stopped by user**")
    else:
        output_lines.append(f"\n\n❌ **Failed** (exit code: {process.returncode})")

    yield "".join(output_lines)


# Create separate generator functions for each slot (can't use lambda with generators)
def run_slot_1(job_url, company_url, questions, provider, resume_variant):
    yield from _run_pipeline(job_url, company_url, questions, provider, resume_variant, 1)

def run_slot_2(job_url, company_url, questions, provider, resume_variant):
    yield from _run_pipeline(job_url, company_url, questions, provider, resume_variant, 2)

def run_slot_3(job_url, company_url, questions, provider, resume_variant):
    yield from _run_pipeline(job_url, company_url, questions, provider, resume_variant, 3)


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
        with gr.Row():
            resume_variant = gr.Radio(
                choices=["Growth PM", "Generalist"],
                value="Growth PM",
                label="Resume",
            )
            provider = gr.Radio(
                choices=["gemini", "groq", "sambanova"],
                value="gemini",
                label="ATS Provider (step 5)",
            )

        with gr.Row():
            submit_btn = gr.Button("▶ Run", variant="primary", scale=3)
            stop_btn = gr.Button("⏹ Stop", variant="stop", scale=1)

        with gr.Accordion("Output", open=True):
            output = gr.Textbox(
                label=None,
                lines=15,
                max_lines=30,
                interactive=False,
                show_label=False,
            )

        with gr.Accordion("Console", open=False):
            console = gr.Textbox(
                label=None,
                value="Console output will appear here when there are errors or debug info.",
                lines=8,
                max_lines=15,
                interactive=False,
                show_label=False,
            )

    return job_url, company_url, questions, provider, resume_variant, submit_btn, stop_btn, output, console


def create_ui():
    """Create the Gradio interface with 3 parallel forms."""
    with gr.Blocks(title="JobQuest", theme=gr.themes.Soft()) as app:
        gr.Markdown("# 🎯 JobQuest")

        with gr.Row():
            stats_display = gr.Markdown(get_stats_display())
            refresh_btn = gr.Button("🔄 Refresh", size="sm", scale=0)

        recent_display = gr.Markdown(get_recent_outputs())

        gr.Markdown("---")

        with gr.Row():
            with gr.Column():
                gr.Markdown("### Application 1")
                j1, c1, q1, p1, r1, b1, s1, o1, con1 = create_app_form(1)

            with gr.Column():
                gr.Markdown("### Application 2")
                j2, c2, q2, p2, r2, b2, s2, o2, con2 = create_app_form(2)

            with gr.Column():
                gr.Markdown("### Application 3")
                j3, c3, q3, p3, r3, b3, s3, o3, con3 = create_app_form(3)

        # Run buttons - use dedicated generator functions (not lambdas)
        b1.click(fn=run_slot_1, inputs=[j1, c1, q1, p1, r1], outputs=[o1], concurrency_limit=None)
        b2.click(fn=run_slot_2, inputs=[j2, c2, q2, p2, r2], outputs=[o2], concurrency_limit=None)
        b3.click(fn=run_slot_3, inputs=[j3, c3, q3, p3, r3], outputs=[o3], concurrency_limit=None)

        # Stop buttons
        s1.click(fn=lambda: stop_process(1), outputs=[con1])
        s2.click(fn=lambda: stop_process(2), outputs=[con2])
        s3.click(fn=lambda: stop_process(3), outputs=[con3])

        def _refresh():
            return get_stats_display(), get_recent_outputs()

        refresh_btn.click(
            fn=_refresh,
            outputs=[stats_display, recent_display],
            concurrency_limit=None,
        )

    return app


if __name__ == "__main__":
    app = create_ui()
    app.queue(default_concurrency_limit=None)
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=True,
    )
