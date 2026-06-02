"""Smoke tests for the JobQuest pipeline.

These tests verify that the pipeline can be imported and run in dry-run mode
without errors. They are designed to catch regressions after code changes.

Run with: pytest tests/ -v
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure .env is loaded for tests that need config
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")


class TestImports:
    """Verify all core modules import without errors."""

    def test_config_imports(self):
        from config import (
            NOTION_TOKEN,
            MASTER_RESUME_ID,
            GEMINI_API_KEY,
            ROLE_VARIANT,
        )
        assert ROLE_VARIANT in ("growth_pm", "generalist", "ai_pm")

    def test_llm_client_imports(self):
        from modules.llm_client import (
            GEMINI_MODELS,
            MODEL_FALLBACK_ORDER,
            DEFAULT_MODEL,
            GeminiClient,
            FallbackClient,
            create_client,
            create_writing_client,
        )
        # Verify model list is valid
        assert len(GEMINI_MODELS) > 0
        assert DEFAULT_MODEL in GEMINI_MODELS
        # Verify no paid-only models leaked in
        assert "gemini-3-1-pro" not in GEMINI_MODELS
        assert "gemini-3-pro" not in GEMINI_MODELS

    def test_scraper_imports(self):
        from modules.scrapers.job_postings import scrape_job_posting
        from modules.scrapers.company_research import research_company
        from modules.job_scraper import scrape_job_posting, research_company

    def test_parsers_imports(self):
        from modules.parsers import (
            fix_markdown_lists,
            extract_latex,
            parse_ats_report,
            parse_qa_answers,
        )

    def test_pipeline_imports(self):
        from modules.pipeline import (
            step_scrape_job,
            step_read_master_resume,
            step_tailor_resume,
            step_compile_pdf,
            step_generate_qa,
            _resume_cache_file,
            _is_ai_heavy_jd,
        )
        # Verify resume cache works
        cache_path = _resume_cache_file("test-id-12345678")
        assert ".master_resume_cache_" in str(cache_path)

    def test_all_providers_registered(self):
        """Every provider in the fallback chain has a corresponding client class."""
        from modules.llm_client import (
            GeminiClient,
            GroqClient,
            SambaNovaClient,
            DeepSeekClient,
            OpenRouterClient,
            AnthropicClient,
            PROVIDER_FALLBACK_ORDER,
        )

        provider_cls_map = {
            "gemini": GeminiClient,
            "groq": GroqClient,
            "sambanova": SambaNovaClient,
            "deepseek": DeepSeekClient,
            "openrouter": OpenRouterClient,
            "anthropic": AnthropicClient,
        }

        for provider in PROVIDER_FALLBACK_ORDER:
            assert provider in provider_cls_map, f"Missing client class for {provider}"


class TestParsers:
    """Verify parsers handle common edge cases."""

    def test_fix_markdown_lists(self):
        from modules.parsers import fix_markdown_lists

        tex_input = (
            "\\section*{Certifications}\n"
            "- Item one\n"
            "- Item two\n"
        )
        result = fix_markdown_lists(tex_input)
        assert "\\begin{itemize}" in result
        assert "\\item Item one" in result
        assert "\\end{itemize}" in result

    def test_extract_latex_fenced(self):
        from modules.parsers import extract_latex

        tex_input = (
            "```latex\n"
            "\\documentclass{article}\n"
            "Some content\n"
            "\\end{document}\n"
            "```"
        )
        result = extract_latex(tex_input)
        assert result is not None
        assert "\\documentclass" in result

    def test_extract_latex_raw(self):
        from modules.parsers import extract_latex

        tex_input = (
            "\\documentclass{article}\n"
            "Some content\n"
            "\\end{document}"
        )
        result = extract_latex(tex_input)
        assert result is not None
        assert "\\documentclass" in result

    def test_parse_qa_pairs(self):
        from modules.parsers import parse_qa_answers

        text = "### Q: Why this role?\n\n### A: Because it fits my experience.\n\n"
        result = parse_qa_answers(text)
        assert len(result) == 1
        assert result[0]["question"] == "Why this role?"

    def test_parse_ats_report_json(self):
        from modules.parsers import parse_ats_report

        text = (
            '```json\n{"coverage_score": {"coverage_pct": 75}}\n```\n'
        )
        result = parse_ats_report(text)
        assert result["json"] is not None
        assert result["json"]["coverage_score"]["coverage_pct"] == 75


class TestPipelineHelpers:
    """Verify pipeline utility functions."""

    def test_ai_heavy_jd_detection_positive(self):
        from modules.pipeline import _is_ai_heavy_jd

        jd = "We need someone who uses AI tools like Claude and Cursor for vibe coding."
        assert _is_ai_heavy_jd(jd) is True

    def test_ai_heavy_jd_detection_negative(self):
        from modules.pipeline import _is_ai_heavy_jd

        jd = "We need a product manager who can lead cross-functional teams."
        assert _is_ai_heavy_jd(jd) is False

    def test_resume_cache_unique_per_id(self):
        from modules.pipeline import _resume_cache_file

        cache_a = _resume_cache_file("aaaa-bbbb-cccc-dddd")
        cache_b = _resume_cache_file("eeee-ffff-gggg-hhhh")
        assert cache_a != cache_b


class TestJobScraperPatterns:
    """Verify URL pattern matching for known ATS platforms."""

    def test_greenhouse_pattern(self):
        from modules.scrapers.job_postings import _GREENHOUSE_PATTERN

        match = _GREENHOUSE_PATTERN.search(
            "https://boards.greenhouse.io/company/jobs/12345"
        )
        assert match is not None
        assert match.group(1) == "company"
        assert match.group(2) == "12345"

    def test_lever_pattern(self):
        from modules.scrapers.job_postings import _LEVER_PATTERN

        match = _LEVER_PATTERN.search(
            "https://jobs.lever.co/company/abc-def-123"
        )
        assert match is not None
        assert match.group(1) == "company"

    def test_ashby_pattern(self):
        from modules.scrapers.job_postings import _ASHBY_PATTERN

        match = _ASHBY_PATTERN.search(
            "https://jobs.ashbyhq.com/company/senior-pm"
        )
        assert match is not None
        assert match.group(1) == "company"


class TestDryRun:
    """Verify the pipeline can execute in dry-run mode.

    This is the most important test — it catches regressions in pipeline wiring.
    """

    def test_build_steps_all_present(self):
        """All pipeline steps should be registered (11 steps with scoring + cover letter)."""
        from apply import build_steps

        steps = build_steps(fill_form=False)
        step_ids = [s[0] for s in steps]
        assert len(steps) == 11, f"Expected 11 steps, got {len(steps)}"
        assert "scrape" in step_ids
        assert "resume" in step_ids
        assert "tailor" in step_ids
        assert "cl" in step_ids
        assert "score" in step_ids
        assert "tracker" in step_ids

    def test_form_filler_optional(self):
        """Form filler should only be included when --fill-form is passed."""
        from apply import build_steps

        steps_default = build_steps(fill_form=False)
        step_ids = [s[0] for s in steps_default]
        assert "form" not in step_ids, "Form filler should be off by default"
        assert len(steps_default) == 11

        steps_enabled = build_steps(fill_form=True)
        step_ids_enabled = [s[0] for s in steps_enabled]
        assert "form" in step_ids_enabled, "Form filler should be included when requested"
        assert len(steps_enabled) == 12

    def test_dry_run_no_api_calls(self):
        """Dry run should not make any API calls."""
        import argparse
        from apply import run_pipeline_from_cli

        args = argparse.Namespace(
            job_url="https://boards.greenhouse.io/example/jobs/99999",
            company_url=None,
            questions=[],
            provider="gemini",
            dry_run=True,
            cover_letter=False,
            cover_letter_instructions=None,
        )
        result = run_pipeline_from_cli(args)
        assert result == 0, f"Dry run failed with exit code {result}"

    def test_scoring_computation(self):
        """Scoring should produce 0-100 with breakdown."""
        from modules.pipeline import compute_pipeline_score

        # Simulate a ctx with all scoring inputs
        ctx = {
            "ats_report": {"json": {"coverage_score": {"coverage_pct": 75}}},
            "tailor_review": "PASS",
            "company_research": "Some research text about the company " * 30,
            "job": {"description": "We use AI tools like Claude and Cursor"},
        }

        from rich.console import Console
        c = Console()
        score = compute_pipeline_score(ctx, c)
        assert 0 <= score <= 100, f"Score {score} out of range"
        assert ctx["pipeline_score"] == round(score)
        assert ctx["pipeline_score_label"] in ("STRONG", "GOOD", "WEAK", "SKIP")
        assert "ats" in ctx["pipeline_score_breakdown"]
        assert "compliance" in ctx["pipeline_score_breakdown"]
        assert "research" in ctx["pipeline_score_breakdown"]
        assert "ai" in ctx["pipeline_score_breakdown"]

    def test_scoring_skip_low(self):
        """Low ATS + no research + failed compliance = SKIP."""
        from modules.pipeline import compute_pipeline_score

        ctx = {
            "ats_report": {"json": {"coverage_score": {"coverage_pct": 25}}},
            "tailor_review": "SEVERITY: HIGH — summary missing",
            "company_research": "",
            "job": {"description": "Standard PM role"},
        }
        from rich.console import Console
        score = compute_pipeline_score(ctx, Console())
        assert score < 60, f"Should be WEAK or SKIP, got {score}"
        assert ctx["pipeline_score_label"] in ("WEAK", "SKIP")
