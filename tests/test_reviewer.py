"""Tests for Drafter-Reviewer agent loop (Spec 005).

Verifies:
- Reviewer prompt exists and has required sections
- create_reviewer_client() returns a working client
- step_review_drafts produces feedback when enabled
- step_apply_review applies JSON edits and logs narrative suggestions
- --skip-reviewer skips the reviewer step
- Reviewer failure is handled gracefully
- Pipeline imports include reviewer steps
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"
sys.path.insert(0, str(PROJECT_ROOT))


# ─── Prompt structure ────────────────────────────────────────────

class TestReviewerPrompt:
    """Verify the reviewer prompt file exists and has required sections."""

    @pytest.fixture(autouse=True)
    def prompt_text(self):
        path = PROMPTS_DIR / "reviewer.md"
        assert path.exists(), f"Reviewer prompt not found: {path}"
        return path.read_text()

    def test_prompt_has_part_a_instructions(self, prompt_text):
        assert "Part A" in prompt_text, (
            "Reviewer prompt must describe Part A (JSON edits) format"
        )
        assert "old_string" in prompt_text, (
            "Part A must include old_string/replacement instructions"
        )

    def test_prompt_has_part_b_instructions(self, prompt_text):
        assert "Part B" in prompt_text, (
            "Reviewer prompt must describe Part B (narrative suggestions) format"
        )
        assert "SUGGESTION:" in prompt_text, (
            "Part B must include SUGGESTION format"
        )

    def test_prompt_has_no_fabricate_rule(self, prompt_text):
        assert "do not fabricate" in prompt_text.lower() or \
               "never fabricate" in prompt_text.lower() or \
               "not fabricate" in prompt_text.lower(), (
            "Prompt must forbid fabricating content"
        )

    def test_prompt_has_review_criteria(self, prompt_text):
        for section in ["Missed Keywords", "Company-Specific", "Tone and Style",
                         "Fabricated Content", "Repetition"]:
            assert section in prompt_text, (
                f"Reviewer prompt must include '{section}' review criteria"
            )


# ─── LLM Client ──────────────────────────────────────────────────

class TestReviewerClient:
    """Verify the reviewer client creation and import."""

    def test_create_reviewer_client_importable(self):
        """create_reviewer_client should be importable from llm_client."""
        from modules.llm_client import create_reviewer_client
        assert callable(create_reviewer_client)

    def test_create_reviewer_client_returns_fallback_client(self):
        """Should return a FallbackClient (not the writing chain)."""
        from modules.llm_client import create_reviewer_client
        # FallbackClient requires API keys — mock the internals
        with patch('modules.llm_client.GeminiClient') as mock_gemini:
            client = create_reviewer_client()
        assert client is not None, "create_reviewer_client() returned None"
        assert "gemini" in client.model_name() or "fallback" in client.model_name(), (
            f"Expected gemini-based fallback, got {client.model_name()}"
        )


# ─── Happy path: reviewer catches issues ─────────────────────────

class TestReviewDraftsHappy:
    """Verify step_review_drafts produces feedback on a draft."""

    @pytest.fixture
    def ctx(self):
        run_dir = PROJECT_ROOT / "output" / "TestCorp_2026-06-04"
        run_dir.mkdir(parents=True, exist_ok=True)
        return {
            "run_dir": str(run_dir),
            "company_safe": "TestCorp",
            "job": {
                "title": "Senior Product Manager",
                "company": "TestCorp",
                "description": "We need someone who knows Kubernetes, landing page optimization, and A/B testing.",
            },
            "master_resume": "### Experience\n\n**Acme Inc.** — Built an e-commerce platform.",
            "tailoring_brief": "Theme: data-driven growth. Emphasize e-commerce experience.",
            "tailored_latex": r"\section*{Experience}\n\textbf{Acme Inc.} — Built an e-commerce platform.",
            "skip_reviewer": False,
        }

    @pytest.fixture
    def mock_reviewer_output(self):
        """Simulate a reviewer catching a missed keyword."""
        return (
            '## Part A \u2014 JSON Edits\n\n'
            '```json\n'
            '[\n'
            '  {"old_string": "Built an e-commerce platform.",'
            '   "new_string": "Built an e-commerce platform, optimized via A/B testing.",'
            '   "reason": "Keyword match: landing page optimization"}\n'
            ']\n'
            '```\n\n'
            '## Part B \u2014 Narrative Suggestions\n\n'
            'SUGGESTION: Add data-driven framing to summary\n'
            'CONTEXT: Summary paragraph at top of resume\n'
            'FIX: Start summary with 8 years driving growth\n'
        )

    def test_review_drafts_produces_feedback(self, ctx, mock_reviewer_output):
        """Reviewer should parse output into structured feedback."""
        with patch("modules.pipeline._get_reviewer_client") as mock_get, \
             patch("modules.pipeline.create_reviewer_client_v2") as mock_rev_v2:
            mock_get.return_value.generate.return_value = mock_reviewer_output
            mock_get.return_value.model_name.return_value = "fallback/gemini"
            mock_rev_v2.return_value = mock_get.return_value

            from modules.pipeline import step_review_drafts
            from rich.console import Console
            c = Console()

            result = step_review_drafts(ctx, None, c)
            feedback = result["review_feedback"]

            assert feedback is not None
            assert "part_a" in feedback
            assert "part_b" in feedback
            assert len(feedback["part_a"]) == 1, f"Got {len(feedback['part_a'])} Part A edits"
            assert feedback["part_a"][0]["reason"] == "Keyword match: landing page optimization"
            assert len(feedback["part_b"]) == 1
            assert "data-driven" in feedback["part_b"][0]

    def test_apply_review_applies_json_edits(self, ctx):
        """step_apply_review should apply Part A edits via string replacement."""
        # The LaTeX uses \n for newlines (repr form), old_string must match exactly
        latex_text = r"\section*{Experience}\n\textbf{Acme Inc.} — Built an e-commerce platform."
        feedback = {
            "part_a": [
                {
                    "old_string": latex_text,
                    "new_string": latex_text + ", optimized via A/B testing.",
                    "reason": "Keyword match: landing page optimization",
                }
            ],
            "part_b": [],
        }
        ctx["review_feedback"] = feedback

        from modules.pipeline import step_apply_review
        from rich.console import Console
        c = Console()

        result = step_apply_review(ctx, None, c)
        latex = result["tailored_latex"]

        assert "optimized via A/B testing" in latex, (
            "Part A edit should be applied to the LaTeX"
        )
        assert r"\textbf{Acme Inc.}" in latex, (
            "Unrelated parts of the LaTeX should be preserved"
        )

    def test_apply_review_logs_narrative_suggestions(self, ctx):
        """Part B suggestions should be saved to run dir."""
        feedback = {
            "part_a": [],
            "part_b": [
                "SUGGESTION: Add Kubernetes mention\nCONTEXT: Skills section\nFIX: Add Kubernetes to Tools list if candidate has experience",
            ],
        }
        ctx["review_feedback"] = feedback

        from modules.pipeline import step_apply_review
        from rich.console import Console
        c = Console()

        result = step_apply_review(ctx, None, c)
        run_dir = Path(ctx["run_dir"])
        sug_file = run_dir / f"review_suggestions_{ctx['company_safe']}.md"

        assert sug_file.exists(), "Part B suggestions should be saved to disk"
        content = sug_file.read_text()
        assert "Kubernetes" in content

        # Cleanup
        sug_file.unlink(missing_ok=True)


# ─── Edge cases ──────────────────────────────────────────────────

class TestReviewDraftsEdgeCases:
    """Edge case handling for reviewer steps."""

    @pytest.fixture
    def ctx(self):
        run_dir = PROJECT_ROOT / "output" / "TestEdge_2026-06-04"
        run_dir.mkdir(parents=True, exist_ok=True)
        return {
            "run_dir": str(run_dir),
            "company_safe": "TestEdge",
            "job": {
                "title": "Product Manager",
                "company": "TestEdge",
                "description": "Product management role.",
            },
            "master_resume": "### Experience\n\n**Firm** — Did product stuff.",
            "tailoring_brief": "General PM role.",
            "tailored_latex": r"\section*{Experience}\n\textbf{Firm} — Did product stuff.",
            "skip_reviewer": False,
        }

    def test_skip_reviewer_flag(self, ctx):
        """--skip-reviewer should set feedback to None and not call LLM."""
        ctx["skip_reviewer"] = True

        from modules.pipeline import step_review_drafts
        from rich.console import Console
        c = Console()

        result = step_review_drafts(ctx, None, c)
        assert result["review_feedback"] is None, (
            "skip_reviewer should set feedback to None"
        )

    def test_no_part_a_edits_still_logs_part_b(self, ctx):
        """When reviewer returns no JSON edits, Part B should still be logged."""
        mock_output = (
            "## Part A — JSON Edits\n\n"
            "```json\n[]\n```\n\n"
            "## Part B — Narrative Suggestions\n\n"
            "SUGGESTION: Summary could be more action-oriented\n"
            "CONTEXT: First paragraph\n"
            "FIX: Rewrite to lead with impact numbers\n"
        )

        with patch("modules.pipeline._get_reviewer_client") as mock_get, \
             patch("modules.pipeline.create_reviewer_client_v2") as mock_rev_v2:
            mock_get.return_value.generate.return_value = mock_output
            mock_get.return_value.model_name.return_value = "fallback/gemini"
            mock_rev_v2.return_value = mock_get.return_value

            from modules.pipeline import step_review_drafts, step_apply_review
            from rich.console import Console
            c = Console()

            result = step_review_drafts(ctx, None, c)
            feedback = result["review_feedback"]

            assert len(feedback["part_a"]) == 0, "No Part A edits expected"
            assert len(feedback["part_b"]) == 1, "Part B should have one suggestion"

            # Apply review should skip cleanly
            result2 = step_apply_review(result, None, c)
            assert result2["tailored_latex"] == ctx["tailored_latex"], (
                "No edits → LaTeX unchanged"
            )

            # Cleanup suggestion file
            sug_file = Path(ctx["run_dir"]) / f"review_suggestions_{ctx['company_safe']}.md"
            sug_file.unlink(missing_ok=True)

    def test_old_string_not_found_skipped(self, ctx):
        """When an edit's old_string doesn't match, skip it gracefully."""
        feedback = {
            "part_a": [
                {
                    "old_string": "THIS TEXT DOES NOT EXIST IN THE LATEX",
                    "new_string": "Should not be applied",
                    "reason": "This edit should be skipped",
                }
            ],
            "part_b": [],
        }
        ctx["review_feedback"] = feedback

        from modules.pipeline import step_apply_review
        from rich.console import Console
        c = Console()

        result = step_apply_review(ctx, None, c)
        latex = result["tailored_latex"]

        assert "Should not be applied" not in latex, (
            "Unmatchable old_string should be skipped, not force-applied"
        )


# ─── Error path ──────────────────────────────────────────────────

class TestReviewDraftsErrors:
    """Graceful handling of reviewer failures."""

    @pytest.fixture
    def ctx(self):
        run_dir = PROJECT_ROOT / "output" / "TestError_2026-06-04"
        run_dir.mkdir(parents=True, exist_ok=True)
        return {
            "run_dir": str(run_dir),
            "company_safe": "TestError",
            "job": {
                "title": "Product Manager",
                "company": "TestError",
                "description": "Product management role.",
            },
            "master_resume": "### Experience\n\n**Firm** — Product work.",
            "tailoring_brief": "General PM role.",
            "tailored_latex": r"\section*{Experience}\n\textbf{Firm} — Product work.",
            "skip_reviewer": False,
        }

    def test_reviewer_llm_failure_continues(self, ctx):
        """When reviewer LLM call fails, pipeline continues without review."""
        with patch("modules.pipeline._get_reviewer_client") as mock_get, \
             patch("modules.pipeline.create_reviewer_client_v2") as mock_rev_v2:
            mock_get.return_value.generate.side_effect = RuntimeError("API quota exhausted")
            mock_get.return_value.model_name.return_value = "fallback/gemini"
            mock_rev_v2.return_value = mock_get.return_value

            from modules.pipeline import step_review_drafts, step_apply_review
            from rich.console import Console
            c = Console()

            result = step_review_drafts(ctx, None, c)
            assert result["review_feedback"] is None, (
                "Failed review should set feedback to None"
            )

            # apply_review should be a no-op with None feedback
            result2 = step_apply_review(result, None, c)
            assert result2["tailored_latex"] == ctx["tailored_latex"], (
                "No review → no changes to LaTeX"
            )

    def test_malformed_json_not_fatal(self, ctx):
        """Malformed Part A JSON should not crash the pipeline."""
        mock_output = (
            "## Part A — JSON Edits\n\n"
            "```json\n"
            "[{bad json that doesn't parse}]\n"
            "```\n\n"
            "## Part B — Narrative Suggestions\n\n"
            "SUGGESTION: This still works\n"
            "CONTEXT: Summary\n"
            "FIX: Make it better\n"
        )

        with patch("modules.pipeline._get_reviewer_client") as mock_get, \
             patch("modules.pipeline.create_reviewer_client_v2") as mock_rev_v2:
            mock_get.return_value.generate.return_value = mock_output
            mock_get.return_value.model_name.return_value = "fallback/gemini"
            mock_rev_v2.return_value = mock_get.return_value

            from modules.pipeline import step_review_drafts, step_apply_review
            from rich.console import Console
            c = Console()

            result = step_review_drafts(ctx, None, c)
            feedback = result["review_feedback"]

            assert len(feedback["part_a"]) == 0, "Malformed JSON → empty Part A"
            assert len(feedback["part_b"]) == 1, "Part B should still parse"
            assert "This still works" in feedback["part_b"][0]

            # Cleanup
            sug_file = Path(ctx["run_dir"]) / f"review_suggestions_{ctx['company_safe']}.md"
            sug_file.unlink(missing_ok=True)


# ─── Integration: pipeline imports ───────────────────────────────

class TestReviewerPipelineIntegration:
    """Verify reviewer steps are importable and wired into build_steps."""

    def test_reviewer_steps_importable(self):
        """Both reviewer steps should be importable from modules.pipeline."""
        from modules.pipeline import step_review_drafts, step_apply_review
        assert callable(step_review_drafts)
        assert callable(step_apply_review)

    def test_reviewer_steps_in_build_steps(self):
        """build_steps should include review and apply_review between write_tex and ats_check."""
        from apply import build_steps
        steps = build_steps(fill_form=False)
        step_ids = [s[0] for s in steps]

        assert "review" in step_ids, "build_steps must include review step"
        assert "apply_review" in step_ids, "build_steps must include apply_review step"

        # Verify ordering: review after write_tex, before ats_check
        write_idx = step_ids.index("write_tex")
        review_idx = step_ids.index("review")
        apply_idx = step_ids.index("apply_review")
        ats_idx = step_ids.index("ats_check")

        assert write_idx < review_idx < apply_idx < ats_idx, (
            f"Steps out of order: write_tex({write_idx}) > "
            f"review({review_idx}) > apply_review({apply_idx}) > ats_check({ats_idx})"
        )

    def test_parser_has_skip_reviewer_flag(self):
        """CLI parser should include --skip-reviewer flag."""
        from apply import parse_args
        parser_args = parse_args(["--skip-reviewer", "https://example.com/jobs/123"])
        assert hasattr(parser_args, 'skip_reviewer'), (
            "parse_args must include skip_reviewer attribute"
        )
        assert parser_args.skip_reviewer is True, (
            "--skip-reviewer flag should set skip_reviewer=True"
        )

    def test_default_skip_reviewer_is_false(self):
        """skip_reviewer should default to False when flag is not passed."""
        from apply import parse_args
        parser_args = parse_args(["https://example.com/jobs/123"])
        assert parser_args.skip_reviewer is False, (
            "skip_reviewer should default to False"
        )
