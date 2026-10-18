#!/usr/bin/env python3
"""JobQuest Browser UI - Gradio-based interface for job applications."""

import subprocess
import signal
import os
from pathlib import Path
from threading import Lock

import gradio as gr  # pyright: ignore[reportMissingImports]

try:
    from modules.llm_client import STAGE_ROUTES  # single source of truth for routing
except Exception:  # pragma: no cover - the UI must still start without routing metadata
    STAGE_ROUTES = {}

PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON = str(PROJECT_ROOT / "venv" / "bin" / "python")
OUTPUT_DIR = PROJECT_ROOT / "output"

RESUME_VARIANTS = {
    "Growth PM": "2f40fd98-227b-8083-a78f-c61c38e55a12",
    "Generalist": "30b0fd98-227b-8195-9649-fe5287cb8cb9",
    # AI-PM: uses Growth PM Notion page as base; swap ID once dedicated page is created in Notion
    "AI-PM": "2f40fd98-227b-8083-a78f-c61c38e55a12",
}

# Store running processes for each slot
running_processes: dict[int, subprocess.Popen[str] | None] = {1: None, 2: None, 3: None}
process_lock = Lock()


# Stage metadata for the read-only routing panel: stage key, label, env prefix.
# Mirrors modules.llm_client.STAGE_ROUTES and the <PREFIX>_* override convention
# implemented by modules.llm_client._create_stage_client.
STAGE_DISPLAY: list[tuple[str, str, str]] = [
    ("fit", "Fit evaluation", "FIT"),
    ("jd", "JD analysis", "JD"),
    ("tailor", "Resume tailoring", "TAILOR"),
    ("reviewer", "Adversarial review", "REVIEWER"),
    ("ats", "ATS keyword check", "ATS"),
    ("qa", "Q&A + cover letter", "QA"),
]

# Retired global-writing settings. The UI never sets or forwards these.
RETIRED_MODEL_ENV = (
    "WRITING_PROVIDER",
    "WRITING_MODEL",
    "GEMINI_WRITING_MODEL",
    "LLM_PROVIDER",
)


def _active_route(stage: str, prefix: str) -> tuple[str, str, str, str]:
    """Resolve a stage's active primary/fallback without building a client.

    Read-only mirror of the <PREFIX>_* lookups in
    modules.llm_client._create_stage_client. Building a real client needs API
    keys, so it must not be required just to render the UI.
    """
    defaults = STAGE_ROUTES.get(stage, {})
    return (
        os.getenv(f"{prefix}_PROVIDER", defaults.get("provider", "openrouter")),
        os.getenv(f"{prefix}_MODEL", defaults.get("model", "")),
        os.getenv(f"{prefix}_FALLBACK_PROVIDER", defaults.get("fallback_provider", "")),
        os.getenv(f"{prefix}_FALLBACK_MODEL", defaults.get("fallback_model", "")),
    )


def get_llm_routing_display() -> str:
    """Read-only summary of the active per-stage LLM routing."""
    if not STAGE_ROUTES:
        return (
            "### LLM Routing (read-only)\n\n"
            "Routing metadata unavailable: `modules.llm_client.STAGE_ROUTES` did not import. "
            "The pipeline still routes per stage through the OpenRouter gateway."
        )

    rows = []
    for stage, label, prefix in STAGE_DISPLAY:
        if stage not in STAGE_ROUTES:
            continue
        primary_provider, primary_model, fb_provider, fb_model = _active_route(stage, prefix)
        primary = f"`{primary_provider} · {primary_model}`" if primary_model else "not set"
        fallback = f"`{fb_provider} · {fb_model}`" if fb_model else "disabled"
        rows.append(f"| {label} | {primary} | {fallback} |")

    return (
        "### LLM Routing (read-only)\n\n"
        "Every stage routes through the **OpenRouter** gateway and is configured "
        "**per stage**: one primary plus at most one declared fallback. "
        "There is no global writing-model selector and no per-application model choice. "
        "Override a stage with its own `_PROVIDER` / `_MODEL` / `_FALLBACK_*` env vars.\n\n"
        "| Stage | Primary | Fallback |\n"
        "|---|---|---|\n" + "\n".join(rows)
    )


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
                except (OSError, ProcessLookupError):
                    pass
        return "No process to stop"


def _run_pipeline(job_url, company_url, questions, resume_variant, generate_cover_letter, cover_letter_instructions, interview_prep, auto_apply, slot_num):
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

    if generate_cover_letter:
        cmd.append("--cover-letter")
        if cover_letter_instructions and cover_letter_instructions.strip():
            cmd.extend(["--cover-letter-instructions", cover_letter_instructions.strip()])

    if interview_prep:
        cmd.append("--interview-prep")

    if auto_apply:
        cmd.append("--auto-apply")

    full_env = os.environ.copy()
    full_env["PYTHONUNBUFFERED"] = "1"
    # Retired global-writing settings: never forwarded to the pipeline. Stage
    # routing is owned by modules/llm_client.py::STAGE_ROUTES.
    for retired in RETIRED_MODEL_ENV:
        full_env.pop(retired, None)
    # Targeted edits (JSON patches) are now the default for all providers, much lower token usage
    full_env["TARGETED_EDITS"] = "1"

    # Override master resume ID and set role variant for the subprocess
    variant_label = resume_variant or "Growth PM"
    resume_id = RESUME_VARIANTS.get(variant_label, RESUME_VARIANTS["Growth PM"])
    full_env["NOTION_MASTER_RESUME_ID"] = resume_id
    role_variant_map = {"Growth PM": "growth_pm", "Generalist": "generalist", "AI-PM": "ai_pm"}
    full_env["ROLE_VARIANT"] = role_variant_map.get(variant_label, variant_label.lower().replace(" ", "_"))

    auto_label = " (auto-apply)" if auto_apply else ""
    yield f"🚀 Starting {variant_label} resume run{auto_label} · LLM routing: OpenRouter, per stage...\n\n"

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
    stdout = process.stdout
    if stdout is None:
        yield "❌ Pipeline started without a readable output stream"
        process.kill()
        return

    try:
        for line in iter(stdout.readline, ''):
            output_lines.append(line)
            yield "".join(output_lines)

        process.wait()
    finally:
        with process_lock:
            running_processes[slot_num] = None

    if process.returncode == 0:
        output_lines.append("\n\n✅ **Complete!**")
    elif process.returncode in (-15, -9):
        output_lines.append("\n\n⏹️ **Stopped by user**")
    else:
        output_lines.append(f"\n\n❌ **Failed** (exit code: {process.returncode})")

    yield "".join(output_lines)


# Create separate generator functions for each slot (can't use lambda with generators)
def run_slot_1(job_url, company_url, questions, resume_variant, generate_cover_letter, cover_letter_instructions, interview_prep, auto_apply):
    yield from _run_pipeline(job_url, company_url, questions, resume_variant, generate_cover_letter, cover_letter_instructions, interview_prep, auto_apply, 1)

def run_slot_2(job_url, company_url, questions, resume_variant, generate_cover_letter, cover_letter_instructions, interview_prep, auto_apply):
    yield from _run_pipeline(job_url, company_url, questions, resume_variant, generate_cover_letter, cover_letter_instructions, interview_prep, auto_apply, 2)

def run_slot_3(job_url, company_url, questions, resume_variant, generate_cover_letter, cover_letter_instructions, interview_prep, auto_apply):
    yield from _run_pipeline(job_url, company_url, questions, resume_variant, generate_cover_letter, cover_letter_instructions, interview_prep, auto_apply, 3)


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
                choices=["Growth PM", "Generalist", "AI-PM"],
                value="Growth PM",
                label="Resume variant",
            )
        with gr.Row():
            generate_cover_letter = gr.Checkbox(
                label="Generate cover letter",
                value=False,
            )
        with gr.Row():
            cover_letter_instructions = gr.Textbox(
                label="Cover letter instructions (optional)",
                placeholder="e.g., Emphasize my Postscript AI experience",
                lines=1,
            )
        with gr.Row():
            interview_prep = gr.Checkbox(
                label="Generate interview prep (post-apply · off by default)",
                value=False,
            )
        with gr.Row():
            auto_apply = gr.Checkbox(
                label="Auto-apply (skip fit evaluation gate)",
                value=False,
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

    return job_url, company_url, questions, resume_variant, generate_cover_letter, cover_letter_instructions, interview_prep, auto_apply, submit_btn, stop_btn, output, console


def create_ui():
    """Create the Gradio interface with 3 parallel forms."""
    with gr.Blocks(title="JobQuest") as app:
        gr.Markdown("# 🎯 JobQuest")

        with gr.Accordion("LLM Routing (read-only · OpenRouter gateway · per stage)", open=True):
            gr.Markdown(get_llm_routing_display())

        with gr.Row():
            recent_display = gr.Markdown(get_recent_outputs())
            refresh_btn = gr.Button("🔄 Refresh", size="sm", scale=0)

        gr.Markdown("---")

        with gr.Row():
            with gr.Column():
                gr.Markdown("### Application 1")
                j1, c1, q1, r1, cl1, cli1, ip1, aa1, b1, s1, o1, con1 = create_app_form(1)

            with gr.Column():
                gr.Markdown("### Application 2")
                j2, c2, q2, r2, cl2, cli2, ip2, aa2, b2, s2, o2, con2 = create_app_form(2)

            with gr.Column():
                gr.Markdown("### Application 3")
                j3, c3, q3, r3, cl3, cli3, ip3, aa3, b3, s3, o3, con3 = create_app_form(3)

        # Run buttons - use dedicated generator functions (not lambdas)
        # No model/provider inputs: routing is stage-specific (STAGE_ROUTES).
        b1.click(fn=run_slot_1, inputs=[j1, c1, q1, r1, cl1, cli1, ip1, aa1], outputs=[o1], concurrency_limit=None)
        b2.click(fn=run_slot_2, inputs=[j2, c2, q2, r2, cl2, cli2, ip2, aa2], outputs=[o2], concurrency_limit=None)
        b3.click(fn=run_slot_3, inputs=[j3, c3, q3, r3, cl3, cli3, ip3, aa3], outputs=[o3], concurrency_limit=None)

        # Stop buttons
        s1.click(fn=lambda: stop_process(1), outputs=[con1])
        s2.click(fn=lambda: stop_process(2), outputs=[con2])
        s3.click(fn=lambda: stop_process(3), outputs=[con3])

        refresh_btn.click(
            fn=get_recent_outputs,
            outputs=[recent_display],
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
        inbrowser=False,
        theme=gr.themes.Soft(),  # pyright: ignore[reportPrivateImportUsage]
    )
