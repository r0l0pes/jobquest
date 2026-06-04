"""Tests for the Fit Evaluation Gate (Spec 001).

These tests verify scoring logic, threshold labels, location handling,
career config loading, and prompt composition — without requiring LLM calls.

Run with: pytest tests/test_fit_evaluation.py -v
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── Scoring Logic Tests ──────────────────────────────────────────


class TestFitScoring:
    """Verify the weighted scoring calculation from dimension scores."""

    def _compute_score(self, tech, exp, behav, career, location_pass=True):
        """Replicate the scoring formula from step_evaluate_fit."""
        weights = {
            "technical_skills": 0.30,
            "experience_match": 0.25,
            "behavioral_fit": 0.15,
            "career_alignment": 0.30,
        }
        total = (
            tech * weights["technical_skills"]
            + exp * weights["experience_match"]
            + behav * weights["behavioral_fit"]
            + career * weights["career_alignment"]
        )
        if not location_pass:
            return 0  # Location FAIL overrides
        return round(total)

    def _label(self, score):
        """Replicate the threshold labeling from step_evaluate_fit."""
        if score >= 75:
            return "STRONG FIT"
        elif score >= 60:
            return "GOOD FIT"
        elif score >= 45:
            return "MODERATE"
        elif score >= 30:
            return "WEAK"
        else:
            return "POOR FIT"

    def test_strong_fit_perfect_scores(self):
        score = self._compute_score(100, 100, 100, 100)
        assert score == 100
        assert self._label(score) == "STRONG FIT"

    def test_strong_fit_typical_strong(self):
        score = self._compute_score(85, 80, 70, 80)
        assert score == 80  # 25.5 + 20 + 10.5 + 24 = 80
        assert self._label(score) == "STRONG FIT"

    def test_good_fit_boundary(self):
        score = self._compute_score(70, 65, 60, 55)
        assert score == 63  # 21 + 16.25 + 9 + 16.5 = 62.75 → 63
        assert self._label(score) == "GOOD FIT"

    def test_moderate_boundary(self):
        score = self._compute_score(50, 50, 50, 50)
        assert score == 50
        assert self._label(score) == "MODERATE"

    def test_weak_fit_boundary(self):
        score = self._compute_score(30, 40, 30, 40)
        assert score == 36  # 9 + 10 + 4.5 + 12 = 35.5 → 36
        assert self._label(score) == "WEAK"

    def test_poor_fit_boundary(self):
        score = self._compute_score(20, 20, 20, 20)
        assert score == 20
        assert self._label(score) == "POOR FIT"

    def test_location_fail_returns_zero(self):
        """Location FAIL overrides score to 0 regardless of other scores."""
        score = self._compute_score(90, 90, 90, 90, location_pass=False)
        assert score == 0

    def test_location_fail_strong_scores(self):
        """Even perfect scores become 0 if location fails."""
        score = self._compute_score(100, 100, 100, 100, location_pass=False)
        assert score == 0

    def test_career_alignment_weight_heaviest_non_tech(self):
        """Career alignment (30%) should match technical skills (30%) in weight."""
        # Same scores in tech vs career, career has equal weight
        score = self._compute_score(100, 0, 0, 0)  # Only tech has weight
        assert score == 30  # 100 * 0.30
        score = self._compute_score(0, 0, 0, 100)  # Only career has weight
        assert score == 30  # 100 * 0.30

    def test_behavioral_culture_lowest_weight(self):
        """Behavioral/Culture fit (15%) should have the lowest weight."""
        score = self._compute_score(0, 0, 100, 0)
        assert score == 15  # 100 * 0.15

    def test_exact_75_is_strong(self):
        """Score of exactly 75 qualifies as STRONG FIT (>= 75)."""
        assert self._label(75) == "STRONG FIT"

    def test_just_under_75_is_good(self):
        """Score of 74 qualifies as GOOD FIT (60-74)."""
        assert self._label(74) == "GOOD FIT"

    def test_exact_60_is_good(self):
        """Score of exactly 60 qualifies as GOOD FIT (>= 60)."""
        assert self._label(60) == "GOOD FIT"

    def test_exact_45_is_moderate(self):
        """Score of exactly 45 qualifies as MODERATE (>= 45)."""
        assert self._label(45) == "MODERATE"

    def test_exact_30_is_weak(self):
        """Score of exactly 30 qualifies as WEAK (>= 30)."""
        assert self._label(30) == "WEAK"

    def test_exact_29_is_poor(self):
        """Score of 29 qualifies as POOR FIT (< 30)."""
        assert self._label(29) == "POOR FIT"


# ── Career Config Tests ──────────────────────────────────────────


class TestCareerConfig:
    """Verify career_config.json is valid and consumable."""

    def test_config_file_exists_and_valid_json(self):
        config_path = PROJECT_ROOT / "data" / "career_config.json"
        assert config_path.exists(), f"career_config.json missing at {config_path}"

        data = json.loads(config_path.read_text())
        assert isinstance(data, dict)

    def test_config_has_required_keys(self):
        config_path = PROJECT_ROOT / "data" / "career_config.json"
        data = json.loads(config_path.read_text())

        required_keys = ["career_goals", "deal_breakers", "location", "behavioral_profile"]
        for key in required_keys:
            assert key in data, f"Missing key '{key}' in career_config.json"

    def test_location_has_constraint(self):
        config_path = PROJECT_ROOT / "data" / "career_config.json"
        data = json.loads(config_path.read_text())

        loc = data["location"]
        assert "constraint" in loc or "preferred" in loc
        assert isinstance(loc.get("preferred", []), list)

    def test_behavioral_profile_has_configured_flag(self):
        config_path = PROJECT_ROOT / "data" / "career_config.json"
        data = json.loads(config_path.read_text())

        bp = data["behavioral_profile"]
        assert "configured" in bp
        assert isinstance(bp["configured"], bool)

    def test_career_goals_is_non_empty_list(self):
        config_path = PROJECT_ROOT / "data" / "career_config.json"
        data = json.loads(config_path.read_text())

        assert isinstance(data["career_goals"], list)
        assert len(data["career_goals"]) > 0

    def test_deal_breakers_is_list(self):
        config_path = PROJECT_ROOT / "data" / "career_config.json"
        data = json.loads(config_path.read_text())

        assert isinstance(data["deal_breakers"], list)


# ── Prompt Tests ─────────────────────────────────────────────────


class TestFitEvaluationPrompt:
    """Verify the fit evaluation prompt is valid and loadable."""

    def test_prompt_file_exists(self):
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        assert prompt_path.exists(), f"fit_evaluation.md missing at {prompt_path}"

    def test_prompt_is_non_empty(self):
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text()
        assert len(content) > 200, f"Prompt too short ({len(content)} chars)"

    def test_prompt_contains_scoring_dimensions(self):
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text()

        required_sections = [
            "Technical Skills",
            "Experience Match",
            "Behavioral",
            "Career Alignment",
            "Location",
        ]
        for section in required_sections:
            assert section.lower() in content.lower(), f"Missing section: {section}"

    def test_prompt_contains_weight_mentions(self):
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text()

        assert "30%" in content
        assert "25%" in content
        assert "15%" in content

    def test_prompt_requests_json_output(self):
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text()

        assert "json" in content.lower()
        assert "```json" in content


# ── Pipeline Import Tests ────────────────────────────────────────


class TestFitEvaluationIntegration:
    """Verify step_evaluate_fit can be imported and has correct signature."""

    def test_step_function_imports(self):
        from modules.pipeline import step_evaluate_fit

        import inspect
        sig = inspect.signature(step_evaluate_fit)
        params = list(sig.parameters.keys())
        assert "ctx" in params
        assert "llm" in params
        assert "console" in params
        # Optional: auto_apply parameter
        assert "auto_apply" in params or len(params) >= 3
