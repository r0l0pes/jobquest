"""Tests for Interview Prep Integration — Spec 004.

Verify prompt loading, step function import, and output structure.
Run with: pytest tests/test_interview_prep.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")


class TestInterviewPrepPrompt:
    """Verify the interview prep prompt file loads correctly."""

    def test_prompt_file_exists(self):
        """Prompt file must exist in prompts/ directory."""
        prompt_path = PROJECT_ROOT / "prompts" / "interview_prep.md"
        assert prompt_path.exists(), "interview_prep.md not found in prompts/"

    def test_prompt_has_required_sections(self):
        """Prompt must cover all output sections: questions, STAR, context."""
        from modules.pipeline import _load_prompt

        prompt = _load_prompt("interview_prep")
        assert len(prompt) > 100, "Prompt too short"
        assert "Question" in prompt or "question" in prompt, "Missing question guidance"
        assert "STAR" in prompt, "Missing STAR matching guidance"
        assert "Company" in prompt or "Research" in prompt, "Missing company context guidance"


class TestStepImport:
    """Verify the step function can be imported and has correct signature."""

    def test_step_exists(self):
        """step_generate_interview_prep must be importable."""
        from modules.pipeline import step_generate_interview_prep

        assert callable(step_generate_interview_prep)

    def test_step_in_build_steps(self):
        """Interview prep must appear in build_steps after QA."""
        from apply import build_steps

        steps = build_steps(fill_form=False)
        step_ids = [s[0] for s in steps]
        assert "interview_prep" in step_ids, "interview_prep step missing from build_steps"

        # Must appear after QA and before score
        qa_idx = step_ids.index("qa")
        ip_idx = step_ids.index("interview_prep")
        score_idx = step_ids.index("score")
        assert qa_idx < ip_idx < score_idx, (
            f"interview_prep ({ip_idx}) must be between qa ({qa_idx}) and score ({score_idx})"
        )


class TestOutputStructure:
    """Verify the step produces a valid output file with all required sections."""

    def test_generates_markdown_with_sections(self):
        """With mocked LLM, verify output file has company context, questions, STAR."""
        from modules.pipeline import step_generate_interview_prep
        from rich.console import Console

        console = Console()

        # Build a ctx with everything the step needs
        ctx = {
            "job": {
                "title": "Senior Product Manager",
                "company": "TestCorp",
                "description": "We need a PM who can lead B2B products and run experiments.",
            },
            "run_dir": str(PROJECT_ROOT / "output" / "TestCorp_2026-06-04"),
            "company_safe": "TestCorp",
            "master_resume": "I am a PM with growth and AI experience.",
            "company_research": "TestCorp launched a new B2B analytics platform in Q1 2026.",
            "qa_answers": [],
        }

        # Create the output directory
        Path(ctx["run_dir"]).mkdir(parents=True, exist_ok=True)

        # Mock the writing client to return a structured interview prep
        mock_client = MagicMock()
        mock_client.model_name.return_value = "mock-model"
        mock_client.generate.return_value = (
            "# Interview Preparation: Senior Product Manager at TestCorp\n\n"
            "## Company Context\n\n"
            "TestCorp launched a new B2B analytics platform in Q1 2026.\n\n"
            "## Likely Questions\n\n"
            "### Technical / Role-Specific\n\n"
            "1. **How do you approach B2B product strategy?**\n"
            "   - **Talking points:** Platform roadmap at FORVIA HELLA\n\n"
            "### Behavioral\n\n"
            "1. **Tell me about a time you led a complex project.**\n"
            "   - **STAR:** B2B Platform at FORVIA HELLA\n\n"
            "### Company-Specific\n\n"
            "1. **Why TestCorp?**\n"
            "   - **Talking points:** B2B analytics platform aligns with HELLA experience\n\n"
            "## Questions to Ask Them\n\n"
            "### About the Role\n\n"
            "- What does success look like in the first 6 months?\n\n"
            "### About the Team\n\n"
            "- How does the team divide work?\n\n"
            "### About Culture\n\n"
            "- What do people who thrive here have in common?\n\n"
            "## STAR Examples (Pre-Selected)\n\n"
            "### 1. B2B Platform at FORVIA HELLA — for \"Leading Complex Projects\"\n\n"
            "**S:** Post-merger B2B e-commerce platform for 60,000+ workshops.\n"
            "**T:** Lead platform roadmap and drive self-service activation.\n"
            "**A:** Redesigned checkout, implemented in-product onboarding.\n"
            "**R:** EUR 12M+ Year 1 revenue, 40% self-service increase.\n\n"
            "## Follow-Up Timeline\n\n"
            "- If no response after 2 weeks: [suggested follow-up]\n"
        )

        with patch("modules.pipeline._get_writing_client", return_value=mock_client):
            result = step_generate_interview_prep(ctx, mock_client, console)

        # Verify ctx was updated
        assert "interview_prep_path" in result, "ctx missing interview_prep_path"
        assert Path(result["interview_prep_path"]).exists(), "Output file not created"

        # Read the output and verify structure
        content = Path(result["interview_prep_path"]).read_text()
        assert "## Company Context" in content, "Missing company context section"
        assert "## Likely Questions" in content, "Missing likely questions section"
        assert "## Questions to Ask Them" in content, "Missing questions-to-ask section"
        assert "## STAR Examples" in content, "Missing STAR examples section"
        assert "## Follow-Up Timeline" in content, "Missing follow-up section"

        # Cleanup
        Path(result["interview_prep_path"]).unlink(missing_ok=True)
        try:
            Path(ctx["run_dir"]).rmdir()
        except OSError:
            pass

    def test_handles_missing_company_research(self):
        """When company_research is empty/missing, step still produces output."""
        from modules.pipeline import step_generate_interview_prep
        from rich.console import Console

        console = Console()

        ctx = {
            "job": {
                "title": "Senior PM",
                "company": "NoResearchCo",
                "description": "We need a PM.",
            },
            "run_dir": str(PROJECT_ROOT / "output" / "NoResearchCo_2026-06-04"),
            "company_safe": "NoResearchCo",
            "master_resume": "I am a PM.",
            # No company_research key
        }

        Path(ctx["run_dir"]).mkdir(parents=True, exist_ok=True)

        mock_client = MagicMock()
        mock_client.model_name.return_value = "mock-model"
        mock_client.generate.return_value = (
            "# Interview Preparation\n\n"
            "## Company Context\n\n"
            "No company research available.\n\n"
            "## Likely Questions\n\n"
            "1. **Question**\n\n"
            "## Questions to Ask Them\n\n"
            "- Ask this\n\n"
            "## STAR Examples\n\n"
            "### 1. Example\n\n"
            "## Follow-Up Timeline\n\n"
            "- Follow up after 2 weeks\n"
        )

        with patch("modules.pipeline._get_writing_client", return_value=mock_client):
            result = step_generate_interview_prep(ctx, mock_client, console)

        assert "interview_prep_path" in result
        content = Path(result["interview_prep_path"]).read_text()
        assert "No company research available" in content

        # Cleanup
        Path(result["interview_prep_path"]).unlink(missing_ok=True)
        try:
            Path(ctx["run_dir"]).rmdir()
        except OSError:
            pass
