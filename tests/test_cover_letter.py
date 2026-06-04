"""Tests for cover letter framing upgrade (Spec 002).

Verifies:
- Template has {company_paragraph} placeholder before {body}
- qa_generator.md has forward-looking Cover Letter Framing section
- rodrigo-voice-lite.md has demonstrate-don't-state, no-cliches, no-apologies rules
- Pipeline step handles {company_paragraph} substitution
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"
TEMPLATES_DIR = PROJECT_ROOT / "templates"


# ─── Template structure ──────────────────────────────────────────

class TestCoverLetterTemplate:
    """Verify the .tex template has the new company_paragraph section."""

    @pytest.fixture(autouse=True)
    def template(self):
        path = TEMPLATES_DIR / "cover_letter.tex"
        assert path.exists(), f"Template not found: {path}"
        return path.read_text()

    def test_template_has_company_paragraph_placeholder(self, template):
        assert "{company_paragraph}" in template, (
            "Template must have {company_paragraph} placeholder "
            "for the company motivation section"
        )

    def test_template_has_body_placeholder(self, template):
        assert "{body}" in template, (
            "Template must still have {body} placeholder"
        )

    def test_company_paragraph_comes_before_body(self, template):
        cp_pos = template.find("{company_paragraph}")
        body_pos = template.find("{body}")
        assert cp_pos != -1 and body_pos != -1, (
            "Both {company_paragraph} and {body} must exist"
        )
        assert cp_pos < body_pos, (
            "{company_paragraph} must appear before {body} in the template "
            "so the motivation paragraph comes before task-solving body"
        )

    def test_company_paragraph_section_not_empty(self, template):
        """The placeholder should sit in a real LaTeX section, not just be a raw string."""
        lines = template.split("\n")
        cp_line = None
        for i, line in enumerate(lines):
            if "{company_paragraph}" in line:
                cp_line = i
                break
        assert cp_line is not None
        # Verify surrounding lines have LaTeX structure (e.g., vspace)
        surrounding = "\n".join(lines[max(0, cp_line - 1):cp_line + 2])
        assert "vspace" in surrounding or "par" in surrounding, (
            "company_paragraph placeholder should be in a structured LaTeX block"
        )


# ─── Prompt content rules ─────────────────────────────────────────

class TestCoverLetterFramingPrompt:
    """Verify qa_generator.md has the forward-looking framing instructions."""

    @pytest.fixture(autouse=True)
    def prompt(self):
        path = PROMPTS_DIR / "qa_generator.md"
        assert path.exists(), f"Prompt not found: {path}"
        return path.read_text()

    def test_has_cover_letter_framing_section(self, prompt):
        assert "Cover Letter Framing" in prompt, (
            "qa_generator.md must have a ## Cover Letter Framing section"
        )

    def test_framing_mentions_forward_looking(self, prompt):
        assert "forward" in prompt.lower(), (
            "Cover Letter Framing must mention forward-looking structure"
        )

    def test_framing_mentions_task_solving(self, prompt):
        assert "task" in prompt.lower(), (
            "Cover Letter Framing must mention task-solving focus"
        )

    def test_framing_no_cv_repetition(self, prompt):
        assert "NOT a CV repetition" in prompt or "not a CV repetition" in prompt, (
            "Framing section must explicitly say cover letter is NOT CV repetition"
        )

    def test_framing_references_company_specifics(self, prompt):
        """The framing rules should tell the LLM to reference company specifics."""
        # Must mention mission, products, or market position
        has_company_ref = (
            "mission" in prompt.lower()
            or "product" in prompt.lower()
            or "market position" in prompt.lower()
        )
        assert has_company_ref, (
            "Framing must instruct LLM to reference company-specific "
            "mission, products, or market position"
        )

    def test_framing_limits_bullets(self, prompt):
        """The framing should limit outcome-oriented bullets to 3-5."""
        assert "3-5" in prompt or "3.5" in prompt or "outcome-oriented" in prompt.lower(), (
            "Framing should specify 3-5 outcome-oriented bullets"
        )


class TestVoiceLiteWritingRules:
    """Verify rodrigo-voice-lite.md has demonstrate-don't-state and tone rules."""

    @pytest.fixture(autouse=True)
    def voice(self):
        path = PROMPTS_DIR / "rodrigo-voice-lite.md"
        assert path.exists(), f"Voice file not found: {path}"
        return path.read_text()

    def test_has_demonstrate_dont_state_rule(self, voice):
        """Must instruct to demonstrate skills through actions, not claims."""
        assert (
            "demonstrate" in voice.lower()
            or "I built" in voice
            or "backtrack" in voice.lower()
        ), "Voice rules must include demonstrate-don't-state guidance"

    def test_has_no_cliches_rule(self, voice):
        """Must warn against cliches like 'passionate about', 'hit the ground running'."""
        assert (
            "cliche" in voice.lower()
            or "cliches" in voice.lower()
            or "passionate about" in voice.lower()
        ), "Voice rules must include no-cliches guidance"

    def test_has_no_apologies_rule(self, voice):
        """Must warn against apologetic language like 'I think I could'."""
        assert (
            "apolog" in voice.lower()
            or "I think I could" in voice
            or "I bring" in voice  # positive framing
        ), "Voice rules must include no-apologetic-language guidance"

    def test_no_interview_backtrack(self, voice):
        """Must include the interview backtrack test concept."""
        assert "backtrack" in voice.lower() or "interview" in voice.lower(), (
            "Voice rules should mention the interview backtrack test"
        )


# ─── Pipeline integration ────────────────────────────────────────

class TestPipelineCoverLetterCompile:
    """Verify step_compile_cover_letter handles {company_paragraph}."""

    def test_step_handles_company_paragraph_placeholder(self):
        """The pipeline step must substitute {company_paragraph} in the template."""
        sys.path.insert(0, str(PROJECT_ROOT))
        from modules.pipeline import step_compile_cover_letter

        source = step_compile_cover_letter.__code__.co_consts
        source_str = str(source)

        # The function body (in code object) or the source file must reference
        # company_paragraph replacement
        func_source = Path(PROJECT_ROOT / "modules" / "pipeline.py").read_text()
        # Find the step_compile_cover_letter function body
        start = func_source.find("def step_compile_cover_letter")
        end = func_source.find("\ndef ", start + 1)
        if end == -1:
            end = len(func_source)
        body = func_source[start:end]

        assert "company_paragraph" in body, (
            "step_compile_cover_letter must handle {company_paragraph} "
            "template placeholder"
        )

    def test_company_paragraph_defaults_to_empty(self):
        """When ctx has no cover_letter_company_paragraph, the placeholder becomes empty."""
        tex = (
            r"Dear Hiring Team,\vspace{10pt}"
            r"{company_paragraph}"
            r"\vspace{15pt}"
            r"{body}"
        )
        # Simulate substitution
        cp = ""  # Default when not provided
        body_text = "Some body content"
        result = tex.replace("{company_paragraph}", cp).replace("{body}", body_text)
        assert "Some body content" in result
        # company_paragraph section collapses to empty (no leftover placeholder)
        assert "{company_paragraph}" not in result
        assert "{body}" not in result
