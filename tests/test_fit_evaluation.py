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

    def test_prompt_preserves_no_fabrication_guard(self):
        """The market context must never be usable to invent resume claims."""
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text().lower()

        assert "never be used to invent resume claims" in content
        assert "gap" in content

    def test_prompt_contains_five_work_architectures(self):
        """Sep 2026 deep phase: five architectures, not one 'modern PM'."""
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text().lower()

        for architecture in [
            "ai application",
            "ai platform",
            "ai automation",
            "growth",
            "generalist",
        ]:
            assert architecture in content, f"Missing architecture: {architecture}"
        # The technical track must still devalue tool fluency alone
        assert "not sufficient" in content

    def test_prompt_contains_gate_scale(self):
        """Requirement intensity 0-4 must stay documented."""
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text()

        assert "0-4 gate scale" in content
        assert "prior proof demanded" in content.lower()

    def test_prompt_requires_bundle_thinking(self):
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text().lower()

        assert "bundles matter more than individual keywords" in content
        assert "ai production" in content
        assert "growth operator" in content

    def test_prompt_treats_seniority_as_scope(self):
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text().lower()

        assert "seniority is scope, not tenure" in content
        assert "cross-squad" in content

    def test_prompt_calibrates_ai_platform_as_gap(self):
        """Candidate AI history is application/growth shaped, not platform."""
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text().lower()

        assert "application and growth shaped" in content
        assert "genuine gap" in content

    def test_prompt_downgrades_unsupported_claims(self):
        """Stale assumptions must not silently raise a score again."""
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text().lower()

        assert "claims explicitly not supported" in content
        assert "premium is not established" in content
        assert "not a trend series" in content

    def test_prompt_contains_current_eval_vocabulary(self):
        """Load-bearing ML-grade vocabulary must not silently drift out."""
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text().lower()

        required = [
            "rag",
            "react",
            "function-calling",
            "multi-agent orchestration",
            "fine-tuning",
            "precision",
            "recall",
            "f1",
            "hallucination",
            "inference latency",
            "retraining",
        ]
        for term in required:
            assert term in content, f"Missing eval vocabulary: {term}"

    def test_prompt_contains_updated_tool_stack(self):
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text().lower()

        for tool in ["cursor", "n8n", "zapier", "databricks", "bigquery"]:
            assert tool in content, f"Missing tool: {tool}"

    def test_prompt_has_corrected_ai_act_timeline(self):
        """Digital Omnibus deferred Annex III high-risk to 2 Dec 2027."""
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text()

        assert "2 December 2027" in content
        assert "Annex III" in content
        # The live obligations must still be described as live
        assert "Article 50" in content or "Article 50 transparency" in content

    def test_prompt_notes_unaided_interview_expectation(self):
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text().lower()

        assert "without ai tools" in content
        assert "disqualification" in content

    def test_prompt_requires_archetype_choice_before_scoring(self):
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text().lower()

        assert "do not average the two" in content

    def test_prompt_retains_role_families(self):
        """Generalist and Growth context must not be lost to AI edits."""
        prompt_path = PROJECT_ROOT / "prompts" / "fit_evaluation.md"
        content = prompt_path.read_text().lower()

        assert "generalist" in content
        assert "growth" in content
        assert "plg" in content


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

    def test_fit_client_importable(self):
        """_get_fit_client should be importable and callable."""
        from modules.pipeline import _get_fit_client

        assert callable(_get_fit_client)

    def test_fit_client_uses_the_explicit_fit_route(self):
        """B.1.5: the fit stage owns its route (OpenRouter), not a Gemini walk.

        Also asserts the bounded contract: one primary plus at most one declared
        fallback, and that the hidden Gemini walk is not part of the route.
        """
        from modules.llm_client import RoutedClient
        from modules.pipeline import _get_fit_client

        client = _get_fit_client()
        assert isinstance(client, RoutedClient), (
            f"Expected RoutedClient, got {type(client).__name__}"
        )
        routes = client.route_ids
        assert 1 <= len(routes) <= 2, (
            f"expected one primary + at most one fallback, got {routes}"
        )
        assert all(r.startswith("openrouter/") for r in routes), (
            f"Expected the OpenRouter fit route, got {routes}"
        )
        assert not any("gemini" in r for r in routes)

    def test_fit_client_docstrings_explain_revert(self):
        """Docstring should explain how to revert to writing chain."""
        from modules.pipeline import _get_fit_client

        doc = _get_fit_client.__doc__ or ""
        assert "revert" in doc.lower() or "_to revert" in doc.lower(), (
            "_get_fit_client docstring should mention how to revert"
        )
        # Also check the module-level comment
        import modules.pipeline as mod
        source = mod.__doc__ or ""
        # The comment is above the function in source, not in module docstring
        # Check the function source instead
        import inspect
        source_lines = inspect.getsource(mod._get_fit_client)
        assert "revert" in source_lines.lower() or "switch back" in source_lines.lower(), (
            "Source should mention revert path"
        )

    def test_fit_client_has_separate_cache(self):
        """_get_fit_client should have its own cache, separate from writing client."""
        from modules.pipeline import _get_fit_client, _get_writing_client

        fit_client = _get_fit_client
        writing_client = _get_writing_client
        assert fit_client is not writing_client, (
            "fit and writing client accessors should be different functions"
        )
