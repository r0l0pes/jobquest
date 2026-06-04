"""Tests for Behavioral Profile layer (Spec 006).

Verifies:
- Behavioral profile prompt exists with required sections
- _load_behavioral_profile() loads correctly
- Fit evaluation receives behavioral profile context
- Q&A generation injects behavioral tone instructions
- Missing profile handles gracefully (empty string)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"
sys.path.insert(0, str(PROJECT_ROOT))


# ─── Prompt structure ────────────────────────────────────────────

class TestBehavioralProfilePrompt:
    """Verify the behavioral profile prompt file exists and has required sections."""

    @pytest.fixture(autouse=True)
    def profile_text(self):
        path = PROMPTS_DIR / "behavioral_profile.md"
        assert path.exists(), f"Behavioral profile not found: {path}"
        return path.read_text()

    def test_profile_has_overview(self, profile_text):
        assert "## Overview" in profile_text, "Profile must have an Overview section"

    def test_profile_has_core_drives(self, profile_text):
        assert "Core Drives" in profile_text, "Profile must have Core Drives table"

    def test_profile_has_communication_style(self, profile_text):
        assert "Communication Style" in profile_text, "Profile must have Communication Style section"

    def test_profile_has_strengths(self, profile_text):
        assert "Strengths" in profile_text, "Profile must have Strengths section"

    def test_profile_has_growth_areas(self, profile_text):
        assert "Growth Areas" in profile_text, "Profile must have Growth Areas section"

    def test_profile_has_thrives_in(self, profile_text):
        assert "Thrives In" in profile_text, "Profile must have Thrives In section"


# ─── Load behavioral profile ────────────────────────────────────

class TestLoadBehavioralProfile:
    """Verify _load_behavioral_profile() loading logic."""

    def test_load_behavioral_profile_importable(self):
        """_load_behavioral_profile should be importable."""
        from modules.pipeline import _load_behavioral_profile
        assert callable(_load_behavioral_profile)

    def test_load_behavioral_profile_returns_string(self):
        """Should return a non-empty string when the profile file exists."""
        from modules.pipeline import _load_behavioral_profile
        profile = _load_behavioral_profile()
        assert isinstance(profile, str)
        assert len(profile) > 100, "Profile should have substantial content"

    def test_load_behavioral_profile_has_core_sections(self):
        """Loaded profile should contain expected sections."""
        from modules.pipeline import _load_behavioral_profile
        profile = _load_behavioral_profile()
        assert "Overview" in profile
        assert "Core Drives" in profile
        assert "Communication Style" in profile

    def test_load_behavioral_profile_empty_when_missing(self):
        """Should return empty string when the file doesn't exist."""
        with patch("modules.pipeline.PROMPTS_DIR", Path("/nonexistent")):
            from modules.pipeline import _load_behavioral_profile
            result = _load_behavioral_profile()
            assert result == "", f"Expected empty string, got: {result!r}"


# ─── Fit evaluation integration ──────────────────────────────────

class TestBehavioralInFitEval:
    """Verify behavioral profile is passed to fit evaluation."""

    def test_fit_eval_receives_behavioral_profile(self, tmp_path):
        """step_evaluate_fit should include behavioral profile in prompt."""
        from modules.pipeline import step_evaluate_fit
        from modules.pipeline import _load_behavioral_profile
        from rich.console import Console

        run_dir = tmp_path / "TestBehave"
        run_dir.mkdir(parents=True, exist_ok=True)

        c = Console()
        ctx = {
            "run_dir": str(run_dir),
            "company_safe": "TestBehave",
            "job": {
                "title": "Senior Product Manager",
                "company": "TestBehave",
                "description": "Product management role with autonomy and data-driven decision making.",
            },
            "master_resume": "### Experience\n\n**Acme Inc.** — Built products."
        }

        with patch("modules.pipeline._get_fit_client") as mock_get:
            mock = MagicMock()
            mock.generate.return_value = '{"dimensions": {"technical_skills": {"score": 70, "note": "Good"}, "experience_match": {"score": 70, "note": "Good"}, "behavioral_fit": {"score": 75, "note": "Profile used"}, "career_alignment": {"score": 70, "note": "Good"}, "location": {"status": "PASS", "note": "OK"}}, "strengths": ["Strength"], "gaps": ["Gap"], "recommendation": "Good fit."}'
            mock_get.return_value = mock

            result = step_evaluate_fit(ctx, None, c)

            # Check the behavioral profile was in the generate call
            generate_kwargs = mock.generate.call_args
            user_prompt = generate_kwargs[0][1] if generate_kwargs else ""

            assert "Behavioral Profile" in user_prompt or "Suitable for autonomous product ownership" in user_prompt, (
                "Fit evaluation prompt should include behavioral profile context"
            )

    def test_fit_eval_without_profile_defaults_neutral(self, tmp_path):
        """When no behavioral profile exists, Culture fit should still work."""
        from modules.pipeline import step_evaluate_fit
        from rich.console import Console

        run_dir = tmp_path / "TestNoBehave"
        run_dir.mkdir(parents=True, exist_ok=True)

        c = Console()
        ctx = {
            "run_dir": str(run_dir),
            "company_safe": "TestNoBehave",
            "job": {
                "title": "Product Manager",
                "company": "TestNoBehave",
                "description": "General PM role.",
            },
            "master_resume": "### Experience\n\n**Firm** — Products."
        }

        with patch("modules.pipeline._get_fit_client") as mock_get:
            with patch("modules.pipeline._load_behavioral_profile", return_value=""):
                mock = MagicMock()
                mock.generate.return_value = '{"dimensions": {"technical_skills": {"score": 60, "note": "OK"}, "experience_match": {"score": 60, "note": "OK"}, "behavioral_fit": {"score": 50, "note": "No behavioral profile configured."}, "career_alignment": {"score": 60, "note": "OK"}, "location": {"status": "PASS", "note": "OK"}}, "strengths": ["S"], "gaps": ["G"], "recommendation": "OK."}'
                mock_get.return_value = mock

                result = step_evaluate_fit(ctx, None, c)
                assert result["fit_score"] is not None


# ─── Q&A integration ─────────────────────────────────────────────

class TestBehavioralInQA:
    """Verify behavioral profile is passed to Q&A generation."""

    def test_qa_receives_behavioral_profile(self, tmp_path):
        """step_generate_qa should include behavioral profile in its user prompt."""
        from modules.pipeline import step_generate_qa
        from rich.console import Console

        run_dir = tmp_path / "TestBehaveQA"
        run_dir.mkdir(parents=True, exist_ok=True)

        c = Console()
        ctx = {
            "run_dir": str(run_dir),
            "company_safe": "TestBehaveQA",
            "job": {
                "title": "Senior Product Manager",
                "company": "TestBehaveQA",
                "description": "PM role.",
            },
            "master_resume": "### Experience\n\n**Acme** — Products.",
            "all_questions": ["Why do you want to work here?"],
            "generate_cover_letter": False,
            "company_url": None,
        }

        with patch("modules.pipeline._get_writing_client") as mock_get:
            with patch("modules.pipeline.research_company", return_value="Company research text."):
                mock = MagicMock()
                mock.generate.return_value = "### Q: Why do you want to work here?\n\n### A: Because I am a good fit.\n\n_Used: Acme | metric | research point_"
                mock.model_name.return_value = "gemini-3.1-flash-lite"
                mock_get.return_value = mock

                from modules.pipeline import _load_voice_prefix
                with patch("modules.pipeline._load_voice_prefix", return_value=""):
                    with patch("modules.pipeline._load_qa_templates", return_value=""):
                        with patch("modules.pipeline._load_ai_pm_context", return_value=""):
                            with patch("modules.pipeline._is_ai_heavy_jd", return_value=False):
                                result = step_generate_qa(ctx, None, c)

                                generate_kwargs = mock.generate.call_args
                                user_prompt = generate_kwargs[0][1] if generate_kwargs else ""

                                assert "Behavioral Profile" in user_prompt, (
                                    "Q&A prompt should include behavioral profile"
                                )

    def test_qa_without_profile_skips_gracefully(self, tmp_path):
        """When no behavioral profile exists, Q&A should still work."""
        from modules.pipeline import step_generate_qa
        from rich.console import Console

        run_dir = tmp_path / "TestNoBehaveQA"
        run_dir.mkdir(parents=True, exist_ok=True)

        c = Console()
        ctx = {
            "run_dir": str(run_dir),
            "company_safe": "TestNoBehaveQA",
            "job": {
                "title": "PM",
                "company": "TestNoBehaveQA",
                "description": "PM role.",
            },
            "master_resume": "### Experience\n\n**Firm** — Products.",
            "all_questions": ["Tell me about yourself."],
            "generate_cover_letter": False,
            "company_url": None,
        }

        with patch("modules.pipeline._get_writing_client") as mock_get:
            with patch("modules.pipeline.research_company", return_value=""):
                with patch("modules.pipeline._load_behavioral_profile", return_value=""):
                    mock = MagicMock()
                    mock.generate.return_value = "### Q: Tell me about yourself.\n\n### A: I build products."
                    mock.model_name.return_value = "gemini-3.1-flash-lite"
                    mock_get.return_value = mock

                    with patch("modules.pipeline._load_voice_prefix", return_value=""):
                        with patch("modules.pipeline._load_qa_templates", return_value=""):
                            with patch("modules.pipeline._load_ai_pm_context", return_value=""):
                                with patch("modules.pipeline._is_ai_heavy_jd", return_value=False):
                                    result = step_generate_qa(ctx, None, c)
                                    # Check user_prompt (args[1]) — not system_prompt which has tone instructions
                                    args, _ = mock.generate.call_args
                                    user_prompt = args[1] if len(args) >= 2 else ""
                                    assert "## Behavioral Profile" not in user_prompt, (
                                        "No behavioral profile section should appear in user prompt"
                                    )


# ─── Reviewer integration ─────────────────────────────────────────

class TestBehavioralInReviewer:
    """Verify behavioral profile is passed to the reviewer step."""

    def test_reviewer_receives_behavioral_profile(self, tmp_path):
        """step_review_drafts should include behavioral profile in its prompt."""
        from modules.pipeline import step_review_drafts
        from rich.console import Console

        run_dir = tmp_path / "TestBehaveReviewer"
        run_dir.mkdir(parents=True, exist_ok=True)

        c = Console()
        ctx = {
            "run_dir": str(run_dir),
            "company_safe": "TestBehaveReviewer",
            "job": {
                "title": "Senior Product Manager",
                "company": "TestBehaveReviewer",
                "description": "Seeking a data-driven PM with autonomy.",
            },
            "master_resume": "### Experience\n\n**Acme** — Built products.",
            "tailored_latex": "% LaTeX resume draft\n\\section{Experience}\n\\textbf{Product Manager} — Acme Inc.",
            "tailoring_brief": "Themes: data-driven, execution speed.",
        }

        with patch("modules.pipeline._get_reviewer_client") as mock_get:
            mock = MagicMock()
            mock.model_name.return_value = "gemini-3-flash-preview"
            mock.generate.return_value = 'SUGGESTION: No issues found.'
            mock_get.return_value = mock

            result = step_review_drafts(ctx, None, c)

            generate_kwargs = mock.generate.call_args
            user_prompt = generate_kwargs[0][1] if generate_kwargs and len(generate_kwargs[0]) >= 2 else ""

            assert "Behavioral Profile" in user_prompt, (
                "Reviewer prompt should include behavioral profile"
            )

    def test_reviewer_without_profile_graceful(self, tmp_path):
        """When no behavioral profile exists, reviewer should still work."""
        from modules.pipeline import step_review_drafts
        from rich.console import Console

        run_dir = tmp_path / "TestNoBehaveReviewer"
        run_dir.mkdir(parents=True, exist_ok=True)

        c = Console()
        ctx = {
            "run_dir": str(run_dir),
            "company_safe": "TestNoBehaveReviewer",
            "job": {
                "title": "PM",
                "company": "TestNoBehaveReviewer",
                "description": "PM role.",
            },
            "master_resume": "### Experience\n\n**Firm** — Products.",
            "tailored_latex": "% LaTeX resume\n\\section{Experience}\n\\textbf{PM} — Firm Co.",
            "tailoring_brief": "Theme: general PM.",
        }

        with patch("modules.pipeline._get_reviewer_client") as mock_get:
            with patch("modules.pipeline._load_behavioral_profile", return_value=""):
                mock = MagicMock()
                mock.model_name.return_value = "gemini-3-flash-preview"
                mock.generate.return_value = 'SUGGESTION: No issues.'
                mock_get.return_value = mock

                result = step_review_drafts(ctx, None, c)

                generate_kwargs = mock.generate.call_args
                user_prompt = generate_kwargs[0][1] if generate_kwargs and len(generate_kwargs[0]) >= 2 else ""

                assert "## Behavioral Profile" not in user_prompt, (
                    "No behavioral profile section when file is missing"
                )

    def test_skip_reviewer_bypasses_behavioral_load(self, tmp_path):
        """When --skip-reviewer is set, behavioral profile loading is irrelevant."""
        from modules.pipeline import step_review_drafts
        from rich.console import Console

        run_dir = tmp_path / "TestSkipReviewer"
        run_dir.mkdir(parents=True, exist_ok=True)

        c = Console()
        ctx = {
            "run_dir": str(run_dir),
            "company_safe": "TestSkipReviewer",
            "skip_reviewer": True,
            "job": {"title": "PM", "company": "TestSkipReviewer", "description": "PM"},
            "master_resume": "Experience",
            "tailored_latex": "LaTeX",
            "tailoring_brief": "Brief",
        }

        with patch("modules.pipeline._get_reviewer_client") as mock_get:
            result = step_review_drafts(ctx, None, c)
            mock_get.assert_not_called()
            assert result["review_feedback"] is None
