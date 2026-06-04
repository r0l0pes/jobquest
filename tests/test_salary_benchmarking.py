"""Tests for Salary Benchmarking Hook (Spec 007).

Verifies:
- SalaryLookup class with fuzzy matching, city filtering
- No data file → graceful skip (not error)
- Company not found → None (not error)
- Integration into fit evaluation and Q&A
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


SAMPLE_DATA = {
    "metadata": {
        "source": "Test data",
        "currency": "EUR",
        "index_label": "Comp Index",
        "index_baseline": 100,
        "baseline_description": "Index 100 = market median for PM roles in Berlin",
    },
    "companies": [
        {
            "company": "Zalando SE",
            "city": "Berlin",
            "categories": {
                "base_salary": {"count": 45, "index": 115.3},
                "total_comp": {"count": 32, "index": 122.1},
            },
        },
        {
            "company": "Delivery Hero SE",
            "city": "Berlin",
            "categories": {
                "base_salary": {"count": 38, "index": 108.7},
                "total_comp": {"count": 25, "index": 118.4},
            },
        },
        {
            "company": "Personio GmbH",
            "city": "Munich",
            "categories": {
                "base_salary": {"count": 18, "index": 112.0},
                "total_comp": {"count": 12, "index": 120.3},
            },
        },
    ],
}


# ─── SalaryLookup class ─────────────────────────────────────────

class TestSalaryLookupInit:
    """Verify SalaryLookup initializes correctly."""

    def test_importable(self):
        """SalaryLookup should be importable."""
        from scripts.salary_lookup import SalaryLookup
        assert callable(SalaryLookup)

    def test_init_with_custom_path(self, tmp_path):
        """Should accept a custom data path."""
        from scripts.salary_lookup import SalaryLookup
        data_file = tmp_path / "test_salary.json"
        data_file.write_text(json.dumps(SAMPLE_DATA))
        lookup = SalaryLookup(data_path=str(data_file))
        assert lookup.has_data() is True

    def test_init_with_missing_file(self, tmp_path):
        """Missing data file should not raise."""
        from scripts.salary_lookup import SalaryLookup
        lookup = SalaryLookup(data_path=str(tmp_path / "nonexistent.json"))
        assert lookup.has_data() is False


class TestSalaryLookupMatching:
    """Verify company name matching logic."""

    @pytest.fixture
    def lookup(self, tmp_path):
        from scripts.salary_lookup import SalaryLookup
        data_file = tmp_path / "salary.json"
        data_file.write_text(json.dumps(SAMPLE_DATA))
        return SalaryLookup(data_path=str(data_file))

    def test_exact_match(self, lookup):
        """Exact company name should match."""
        result = lookup.lookup("Zalando SE")
        assert result is not None
        assert result["company"] == "Zalando SE"
        assert "categories" in result

    def test_short_name_match(self, lookup):
        """Short name without legal suffix should match."""
        result = lookup.lookup("Zalando")
        assert result is not None
        assert "Zalando" in result["company"]

    def test_city_filter_match(self, lookup):
        """City filter should return result when city matches."""
        result = lookup.lookup("Zalando", "Berlin")
        assert result is not None
        assert result["city"] == "Berlin"

    def test_city_filter_mismatch(self, lookup):
        """City filter should return None when city doesn't match."""
        result = lookup.lookup("Zalando", "Hamburg")
        assert result is None, "City mismatch should return None"

    def test_fuzzy_match_similar_name(self, lookup):
        """Similar but not exact names should match via fuzzy matching."""
        result = lookup.lookup("Delivery Hero")
        assert result is not None
        assert "Delivery Hero" in result["company"]

    def test_no_match_returns_none(self, lookup):
        """Completely different name should return None."""
        result = lookup.lookup("Google")
        assert result is None

    def test_empty_company_returns_none(self, lookup):
        """Empty company name should return None."""
        result = lookup.lookup("")
        assert result is None

    def test_has_data_true(self, lookup):
        """has_data should return True with valid data."""
        assert lookup.has_data() is True

    def test_salary_data_includes_indices(self, lookup):
        """Matched result should include category indices."""
        result = lookup.lookup("Zalando")
        cats = result["categories"]
        assert "base_salary" in cats
        assert "total_comp" in cats
        assert cats["base_salary"]["index"] == 115.3
        assert cats["base_salary"]["count"] == 45

    def test_list_all_returns_entries(self, lookup):
        """list_all should return all companies."""
        entries = lookup.list_all()
        assert len(entries) == 3


class TestSalaryLookupNoData:
    """Behavior when no salary data exists."""

    def test_no_data_file_graceful(self, tmp_path):
        """No data file should return None, not raise."""
        from scripts.salary_lookup import SalaryLookup
        lookup = SalaryLookup(data_path=str(tmp_path / "nonexistent.json"))
        result = lookup.lookup("Zalando")
        assert result is None

    def test_has_data_false_when_no_file(self, tmp_path):
        """has_data should return False when file missing."""
        from scripts.salary_lookup import SalaryLookup
        lookup = SalaryLookup(data_path=str(tmp_path / "nope.json"))
        assert lookup.has_data() is False

    def test_list_all_empty_when_no_file(self, tmp_path):
        """list_all should return empty list when no data."""
        from scripts.salary_lookup import SalaryLookup
        lookup = SalaryLookup(data_path=str(tmp_path / "nope.json"))
        assert lookup.list_all() == []


# ─── Pipeline integration — fit evaluation ──────────────────────

class TestSalaryInFitEval:
    """Verify salary benchmarking appears in fit evaluation."""

    def test_salary_data_in_fit_eval_context(self, tmp_path):
        """step_evaluate_fit should add salary_benchmark to ctx when data found."""
        from modules.pipeline import step_evaluate_fit
        from rich.console import Console

        run_dir = tmp_path / "TestSalaryFit"
        run_dir.mkdir(parents=True)

        c = Console()
        ctx = {
            "run_dir": str(run_dir),
            "company_safe": "TestSalaryFit",
            "job": {
                "title": "Senior Product Manager",
                "company": "Zalando",
                "description": "PM role.",
                "location": "Berlin",
            },
            "master_resume": "### Experience\n\n**Acme** — Products.",
        }

        with patch("modules.pipeline._get_fit_client") as mock_get:
            with patch("modules.pipeline._load_behavioral_profile", return_value=""):
                with patch("modules.pipeline._get_salary_benchmark") as mock_salary:
                    mock_salary.return_value = {
                        "company": "Zalando SE",
                        "city": "Berlin",
                        "currency": "EUR",
                        "baseline_description": "Index 100 = market median",
                        "categories": {
                            "base_salary": {"count": 45, "index": 115.3},
                            "total_comp": {"count": 32, "index": 122.1},
                        },
                    }
                    mock = MagicMock()
                    mock.generate.return_value = '{"dimensions": {"technical_skills": {"score": 70, "note": "Good"}, "experience_match": {"score": 70, "note": "Good"}, "behavioral_fit": {"score": 60, "note": "OK"}, "career_alignment": {"score": 70, "note": "Good"}, "location": {"status": "PASS", "note": "OK"}}, "strengths": ["S"], "gaps": ["G"], "recommendation": "Good."}'
                    mock_get.return_value = mock

                    result = step_evaluate_fit(ctx, None, c)
                    assert "salary_benchmark" in result
                    assert result["salary_benchmark"]["company"] == "Zalando SE"

    def test_no_salary_data_skips(self, tmp_path):
        """When salary data not found, fit eval should proceed without salary section."""
        from modules.pipeline import step_evaluate_fit
        from rich.console import Console

        run_dir = tmp_path / "TestNoSalary"
        run_dir.mkdir(parents=True)

        c = Console()
        ctx = {
            "run_dir": str(run_dir),
            "company_safe": "TestNoSalary",
            "job": {
                "title": "PM",
                "company": "UnknownCompany",
                "description": "PM role.",
            },
            "master_resume": "### Experience\n\n**Firm** — Products.",
        }

        with patch("modules.pipeline._get_fit_client") as mock_get:
            with patch("modules.pipeline._load_behavioral_profile", return_value=""):
                with patch("modules.pipeline._get_salary_benchmark", return_value=None):
                    mock = MagicMock()
                    mock.generate.return_value = '{"dimensions": {"technical_skills": {"score": 60, "note": "OK"}, "experience_match": {"score": 60, "note": "OK"}, "behavioral_fit": {"score": 50, "note": "Neutral"}, "career_alignment": {"score": 60, "note": "OK"}, "location": {"status": "PASS", "note": "OK"}}, "strengths": ["S"], "gaps": ["G"], "recommendation": "OK."}'
                    mock_get.return_value = mock

                    result = step_evaluate_fit(ctx, None, c)
                    assert "salary_benchmark" not in result or result["salary_benchmark"] is None


# ─── Pipeline integration — Q&A generation ──────────────────────

class TestSalaryInQA:
    """Verify salary context is injected into Q&A prompt."""

    def test_salary_data_in_qa_prompt(self, tmp_path):
        """When salary data exists, Q&A prompt should include salary context section."""
        from modules.pipeline import step_generate_qa
        from rich.console import Console

        run_dir = tmp_path / "TestSalaryQA"
        run_dir.mkdir(parents=True)

        c = Console()
        ctx = {
            "run_dir": str(run_dir),
            "company_safe": "TestSalaryQA",
            "job": {
                "title": "Senior PM",
                "company": "Zalando",
                "description": "PM role.",
            },
            "master_resume": "### Experience\n\n**Acme** — Work.",
            "all_questions": ["What are your salary expectations?"],
            "generate_cover_letter": False,
            "company_url": None,
            "salary_benchmark": {
                "company": "Zalando SE",
                "city": "Berlin",
                "currency": "EUR",
                "categories": {
                    "base_salary": {"count": 45, "index": 115.3},
                },
            },
        }

        with patch("modules.pipeline._get_writing_client") as mock_get:
            with patch("modules.pipeline.research_company", return_value=""):
                with patch("modules.pipeline._load_behavioral_profile", return_value=""):
                    mock = MagicMock()
                    mock.generate.return_value = "### Q: Salary expectations?\n\n### A: Based on market data..."
                    mock.model_name.return_value = "gemini-3.1-flash-lite"
                    mock_get.return_value = mock

                    with patch("modules.pipeline._load_voice_prefix", return_value=""):
                        with patch("modules.pipeline._load_qa_templates", return_value=""):
                            with patch("modules.pipeline._load_ai_pm_context", return_value=""):
                                with patch("modules.pipeline._is_ai_heavy_jd", return_value=False):
                                    result = step_generate_qa(ctx, None, c)

                                    # Verify the generate call included salary context
                                    args, _ = mock.generate.call_args
                                    user_prompt = args[1] if len(args) >= 2 else ""
                                    assert "## Salary Context" in user_prompt
                                    assert "Zalando" in user_prompt
                                    assert "base_salary" in user_prompt or "Base Salary" in user_prompt
                                    assert "market" in user_prompt

    def test_no_salary_in_qa_skips(self, tmp_path):
        """When no salary data exists, Q&A prompt should not include salary section."""
        from modules.pipeline import step_generate_qa
        from rich.console import Console

        run_dir = tmp_path / "TestNoSalaryQA"
        run_dir.mkdir(parents=True)

        c = Console()
        ctx = {
            "run_dir": str(run_dir),
            "company_safe": "TestNoSalaryQA",
            "job": {
                "title": "PM",
                "company": "Unknown",
                "description": "PM role.",
            },
            "master_resume": "### Experience\n\n**Firm** — Work.",
            "all_questions": ["What are your salary expectations?"],
            "generate_cover_letter": False,
            "company_url": None,
        }

        with patch("modules.pipeline._get_writing_client") as mock_get:
            with patch("modules.pipeline.research_company", return_value=""):
                with patch("modules.pipeline._load_behavioral_profile", return_value=""):
                    mock = MagicMock()
                    mock.generate.return_value = "### Q: Salary expectations?\n\n### A: [fill in]"
                    mock.model_name.return_value = "gemini-3.1-flash-lite"
                    mock_get.return_value = mock

                    with patch("modules.pipeline._load_voice_prefix", return_value=""):
                        with patch("modules.pipeline._load_qa_templates", return_value=""):
                            with patch("modules.pipeline._load_ai_pm_context", return_value=""):
                                with patch("modules.pipeline._is_ai_heavy_jd", return_value=False):
                                    result = step_generate_qa(ctx, None, c)

                                    args, _ = mock.generate.call_args
                                    user_prompt = args[1] if len(args) >= 2 else ""
                                    assert "## Salary Context" not in user_prompt, (
                                        "No salary data → no Salary Context section"
                                    )
