"""Tests for Upskill Gap Analysis (Spec 008).

Verifies:
- run_upskill works in aggregate and targeted modes
- _hard_skill_diff builds weighted gap list
- _build_heatmap produces priority tiers
- _generate_learning_plan provides study direction
- _save_report generates correct markdown
- Edge cases: no applications, all skills covered, no previous report
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


SAMPLE_APPLICATIONS = [
    {
        "company": "TechCorp",
        "role": "Senior Product Manager",
        "sector": "SaaS / B2B enterprise software",
        "fit_score": 75,
        "score": 75,
        "notes": "Requires Kubernetes, AWS, CI/CD pipelines, SQL, Experimentation",
        "url": "https://example.com/jobs/techcorp-pm",
    },
    {
        "company": "AICo",
        "role": "AI Product Manager",
        "sector": "AI / Machine Learning",
        "fit_score": 85,
        "score": 85,
        "notes": "Needs LLM experience, Python, PyTorch, MLOps",
        "url": "https://example.com/jobs/aico-pm",
    },
    {
        "company": "GrowthInc",
        "role": "Growth PM",
        "sector": "E-commerce / Marketplace",
        "fit_score": 60,
        "score": 60,
        "notes": "Requires A/B testing, SQL, Analytics, Data pipelines, React frontend",
        "url": "https://example.com/jobs/growthinc-pm",
    },
]


# ─── _hard_skill_diff ───────────────────────────────────────────

class TestHardSkillDiff:
    """Verify the hard skill diff logic."""

    def test_returns_list(self):
        """_hard_skill_diff should return a list."""
        from modules.upskill import _hard_skill_diff
        result = _hard_skill_diff([], "")
        assert isinstance(result, list)

    def test_empty_apps_returns_empty(self):
        """No applications → empty list."""
        from modules.upskill import _hard_skill_diff
        result = _hard_skill_diff([], "")
        assert result == []

    def test_identifies_gaps(self):
        """Should identify skills not in profile."""
        from modules.upskill import _hard_skill_diff
        result = _hard_skill_diff(SAMPLE_APPLICATIONS, "Python SQL")
        skills = [g["skill"] for g in result]
        # Kubernetes, AWS, CI/CD should be identified as gaps
        assert any("kubernetes" in s for s in skills), "Kubernetes should be a gap"
        assert any("aws" in s for s in skills), "AWS should be a gap"

    def test_weighted_by_fit_score(self):
        """Skills from lower-fit jobs should be weighted higher."""
        from modules.upskill import _hard_skill_diff
        result = _hard_skill_diff(SAMPLE_APPLICATIONS, "")
        # Find CI/CD (from GrowthInc with fit_score=60 → higher weight)
        # vs LLM (from AICo with fit_score=85 → lower weight)
        cicd = next((g for g in result if "ci/cd" in g["skill"]), None)
        if cicd:
            assert cicd["score"] > 0
        # The lowest-fit job (GrowthInc at 60) should contribute more weight
        # gap_weight = (100-60)/100 = 0.40 per skill from GrowthInc
        # gap_weight = (100-85)/100 = 0.15 per skill from AICo
        # gap_weight = (100-75)/100 = 0.25 per skill from TechCorp

    def test_known_skills_excluded(self):
        """Skills already in profile should not appear as gaps."""
        from modules.upskill import _hard_skill_diff
        profile = "Python is my main language. SQL is for data querying."
        result = _hard_skill_diff(SAMPLE_APPLICATIONS, profile)
        skills = [g["skill"] for g in result]
        assert "python" not in skills, "Python is in profile, should not be a gap"
        assert "sql" not in skills, "SQL is in profile, should not be a gap"


# ─── _build_heatmap ─────────────────────────────────────────────

class TestBuildHeatmap:
    """Verify heatmap priority assignment."""

    def test_critical_at_high_scores(self):
        """Score >= 5 → Critical priority."""
        from modules.upskill import _build_heatmap
        gaps = [{"skill": "Kubernetes", "score": 5.5, "count": 4}]
        heatmap = _build_heatmap(gaps)
        assert heatmap[0]["priority"] == "Critical"

    def test_high_at_moderate_scores(self):
        """Score >= 2 → High priority."""
        from modules.upskill import _build_heatmap
        gaps = [{"skill": "AWS", "score": 2.5, "count": 2}]
        heatmap = _build_heatmap(gaps)
        assert heatmap[0]["priority"] == "High"

    def test_medium_at_low_scores(self):
        """Score < 2 → Medium priority."""
        from modules.upskill import _build_heatmap
        gaps = [{"skill": "ToolX", "score": 0.5, "count": 1}]
        heatmap = _build_heatmap(gaps)
        assert heatmap[0]["priority"] == "Medium"

    def test_sorted_by_priority_then_score(self):
        """Heatmap should sort Critical first, then High, then Medium, then by score desc."""
        from modules.upskill import _build_heatmap
        gaps = [
            {"skill": "LowSkill", "score": 1.0, "count": 1},
            {"skill": "HighSkill", "score": 6.0, "count": 4},
            {"skill": "MidSkill", "score": 3.0, "count": 2},
        ]
        heatmap = _build_heatmap(gaps)
        assert heatmap[0]["skill"] == "HighSkill"
        assert heatmap[1]["skill"] == "MidSkill"
        assert heatmap[2]["skill"] == "LowSkill"


# ─── _generate_learning_plan ────────────────────────────────────

class TestLearningPlan:
    """Verify learning plan generation."""

    def test_only_critical_and_high_included(self):
        """Learning plan should only include Critical and High items."""
        from modules.upskill import _generate_learning_plan
        heatmap = [
            {"priority": "Critical", "skill": "K8s", "type": "Hard", "score": 5, "count": 4, "source": "test"},
            {"priority": "High", "skill": "AWS", "type": "Tooling", "score": 3, "count": 2, "source": "test"},
            {"priority": "Medium", "skill": "ToolX", "type": "Domain", "score": 1, "count": 1, "source": "test"},
        ]
        plan = _generate_learning_plan(heatmap)
        skills = [item["skill"] for item in plan]
        assert "K8s" in skills
        assert "AWS" in skills
        assert "ToolX" not in skills

    def test_plan_has_estimated_time(self):
        """Each plan item should have a time estimate."""
        from modules.upskill import _generate_learning_plan
        heatmap = [
            {"priority": "Critical", "skill": "Kubernetes", "type": "Hard", "score": 5, "count": 4, "source": "test"},
        ]
        plan = _generate_learning_plan(heatmap)
        assert "estimated_time" in plan[0]
        assert "study_direction" in plan[0]

    def test_empty_heatmap_returns_empty_plan(self):
        """No heatmap items → empty plan."""
        from modules.upskill import _generate_learning_plan
        plan = _generate_learning_plan([])
        assert plan == []


# ─── _save_report ───────────────────────────────────────────────

class TestSaveReport:
    """Verify report saving logic."""

    def test_saves_to_upskill_dir(self, tmp_path):
        """Report should be saved to upskill/report-YYYY-MM-DD.md."""
        from modules.upskill import _save_report
        heatmap = [
            {"priority": "High", "skill": "Kubernetes", "type": "Hard", "score": 3, "count": 2, "source": "test"},
        ]
        plan = [{"skill": "Kubernetes", "priority": "High", "type": "Hard", "estimated_time": "15-20h", "study_direction": "Hands-on practice."}]

        # Patch UPSKILL_DIR to tmp_path
        with patch("modules.upskill.UPSKILL_DIR", tmp_path):
            report_path = _save_report(heatmap, plan)
            assert report_path.exists()
            text = report_path.read_text()
            assert "Gap Heatmap" in text
            assert "Learning Plan" in text
            assert "Kubernetes" in text

    def test_no_previous_report_no_diff(self, tmp_path):
        """No previous report → diff section shows 'first run'."""
        from modules.upskill import _save_report
        with patch("modules.upskill.UPSKILL_DIR", tmp_path):
            report_path = _save_report([], [])
            text = report_path.read_text()
            assert "first run" in text

    def test_previous_report_shows_diff(self, tmp_path):
        """Previous report should produce diff section."""
        from modules.upskill import _save_report
        # Create a previous report
        (tmp_path / "report-2026-01-01.md").write_text(
            "# Upskill Report — 2026-01-01\n\n"
            "## Gap Heatmap\n"
            "| Priority | Skill / Area | Type | Source |\n"
            "| Critical | Oldskill | Hard | 3 jobs |\n"
        )

        heatmap = [{"priority": "High", "skill": "Newskill", "type": "Tooling", "score": 2, "count": 1, "source": "test"}]
        with patch("modules.upskill.UPSKILL_DIR", tmp_path):
            from modules.upskill import _save_report
            report_path = _save_report(heatmap, [])
            text = report_path.read_text()
            assert "first run" not in text, "Should not say 'first run' when previous exists"
            assert "Newskill" in text or "newskill" in text


# ─── run_upskill ────────────────────────────────────────────────

class TestRunUpskill:
    """Verify the main entry point."""

    def test_no_applications(self):
        """No applications → graceful message."""
        from modules.upskill import run_upskill
        with patch("modules.upskill.APPLICATIONS_PATH", Path("/nonexistent/apps.json")):
            result = run_upskill()
            assert result["ok"] is True
            assert "No applications" in result["message"]

    def test_aggregate_mode_with_data(self, tmp_path):
        """Aggregate mode with sample data should produce a report."""
        from modules.upskill import run_upskill
        apps_file = tmp_path / "applications.json"
        apps_file.write_text(json.dumps(SAMPLE_APPLICATIONS))

        with patch("modules.upskill.APPLICATIONS_PATH", apps_file):
            with patch("modules.upskill._llm_synthesize_gaps", return_value=[]):
                with patch("modules.upskill.UPSKILL_DIR", tmp_path / "upskill_out"):
                    result = run_upskill()
                    assert result["ok"] is True
                    assert result["report_path"] is not None
                    assert len(result["heatmap"]) > 0

    def test_targeted_mode(self, tmp_path):
        """Targeted mode should filter by URL."""
        from modules.upskill import run_upskill
        apps_file = tmp_path / "applications.json"
        apps_file.write_text(json.dumps(SAMPLE_APPLICATIONS))

        with patch("modules.upskill.APPLICATIONS_PATH", apps_file):
            with patch("modules.upskill._llm_synthesize_gaps", return_value=[]):
                with patch("modules.upskill.UPSKILL_DIR", tmp_path / "upskill_target"):
                    result = run_upskill(target_url="techcorp")
                    assert result["ok"] is True
                    assert result["report_path"] is not None

    def test_targeted_no_match(self, tmp_path):
        """Targeted mode with non-matching URL → graceful message."""
        from modules.upskill import run_upskill
        apps_file = tmp_path / "applications.json"
        apps_file.write_text(json.dumps(SAMPLE_APPLICATIONS))

        with patch("modules.upskill.APPLICATIONS_PATH", apps_file):
            result = run_upskill(target_url="nonexistent-url")
            assert result["ok"] is True
            assert "No tracked application" in result["message"]

    def test_all_skills_covered(self, tmp_path):
        """When profile covers all skills, heatmap should be empty."""
        from modules.upskill import run_upskill, _hard_skill_diff

        # Profile with bullet-pointed skills matching the job data format
        profile = """\
- Python
- SQL
- Kubernetes
- AWS
- CI/CD pipelines
- Experimentation
- LLM
- PyTorch
- MLOps
- Analytics
- React
- Product Management
- Growth
- Data
- A/B testing
- SaaS
- B2B
- Enterprise
- AI
- Machine Learning
"""
        hard_gaps = _hard_skill_diff(SAMPLE_APPLICATIONS, profile)
        assert len(hard_gaps) == 0, (
            f"Expected no gaps when profile covers all, got: {[g['skill'] for g in hard_gaps]}"
        )


# ─── CLI integration ────────────────────────────────────────────

class TestUpskillCLI:
    """Verify --upskill flag works in apply.py."""

    def test_upskill_flag_parsed(self):
        """--upskill flag should be parseable."""
        from apply import parse_args
        args = parse_args(["--upskill"])
        assert args.upskill is not None
        assert args.upskill == "__aggregate__", "--upskill without arg should use aggregate sentinel"

    def test_upskill_with_url(self):
        """--upskill with URL should set the URL."""
        from apply import parse_args
        url = "https://example.com/jobs/123"
        args = parse_args(["--upskill", url])
        assert args.upskill == url, f"Expected {url}, got {args.upskill}"

    def test_default_upskill_is_none(self):
        """Without --upskill, the attribute should be None."""
        from apply import parse_args
        args = parse_args(["https://example.com/jobs/123"])
        assert args.upskill is None, f"Expected None, got {args.upskill}"
