"""Tests for structured job post schema and validation."""

import pytest
from modules.schemas.job_post import JobPost, validate_job_post


class TestJobPostSchema:
    """JobPost TypedDict shape tests."""

    def test_required_fields_only(self):
        """Minimal job post with required fields passes."""
        post = JobPost(
            title="PM",
            company="Acme",
            description="A job",
            url="https://example.com",
            source="test",
            questions=[],
        )
        assert post["title"] == "PM"
        assert post["company"] == "Acme"

    def test_all_structured_fields(self):
        """JobPost accepts all optional structured fields."""
        post = JobPost(
            title="Senior PM",
            company="Acme Corp",
            description="Full job description...",
            url="https://jobs.example.com/1",
            source="greenhouse_api",
            questions=["Why us?"],
            salary_range="€80k-100k",
            location="Berlin",
            remote_policy="hybrid",
            employment_type="full_time",
            department="Growth",
            required_skills=["Python", "SQL", "A/B Testing"],
            nice_to_have_skills=["Looker", "dbt"],
            posted_date="2026-07-01",
        )
        assert post["salary_range"] == "€80k-100k"
        assert post["remote_policy"] == "hybrid"
        assert post["required_skills"] == ["Python", "SQL", "A/B Testing"]

    def test_partial_structured_fields(self):
        """JobPost with some optional fields works fine."""
        post: JobPost = {
            "title": "PM",
            "company": "Acme",
            "description": "...",
            "url": "https://example.com",
            "source": "test",
            "questions": [],
            "remote_policy": "fully_remote",
        }
        assert post["remote_policy"] == "fully_remote"
        # Unset optional field returns empty list (TypedDict default)
        assert post.get("required_skills") is None


class TestValidateJobPost:
    """Validation function tests."""

    def test_passes_with_minimum_fields(self):
        """Minimum required fields pass validation."""
        data = {
            "title": "PM",
            "company": "Acme",
            "url": "https://example.com",
            "description": "...",
            "source": "test",
            "questions": [],
        }
        result = validate_job_post(data)
        assert result is data  # Pass-through

    def test_passes_with_all_fields(self):
        """Full job post passes validation."""
        data = {
            "title": "Senior PM",
            "company": "Acme",
            "url": "https://example.com",
            "description": "...",
            "source": "test",
            "questions": [],
            "salary_range": "€80k-100k",
            "required_skills": ["Python"],
        }
        result = validate_job_post(data)
        assert result is data

    def test_raises_on_missing_title(self):
        """Missing title raises ValueError."""
        data = {
            "company": "Acme",
            "url": "https://example.com",
            "description": "...",
            "source": "test",
            "questions": [],
        }
        with pytest.raises(ValueError, match="title"):
            validate_job_post(data)

    def test_raises_on_missing_company(self):
        """Missing company raises ValueError."""
        data = {
            "title": "PM",
            "url": "https://example.com",
            "description": "...",
            "source": "test",
            "questions": [],
        }
        with pytest.raises(ValueError, match="company"):
            validate_job_post(data)

    def test_raises_on_missing_url(self):
        """Missing URL raises ValueError."""
        data = {
            "title": "PM",
            "company": "Acme",
            "description": "...",
            "source": "test",
            "questions": [],
        }
        with pytest.raises(ValueError, match="url"):
            validate_job_post(data)

    def test_raises_on_empty_title(self):
        """Empty string title counts as missing."""
        data = {
            "title": "",
            "company": "Acme",
            "url": "https://example.com",
        }
        with pytest.raises(ValueError, match="title"):
            validate_job_post(data)

    def test_missing_all_required(self):
        """Error message lists all missing fields."""
        data = {"description": "no required fields at all"}
        with pytest.raises(ValueError) as exc:
            validate_job_post(data)
        msg = str(exc.value)
        assert "title" in msg
        assert "company" in msg
        assert "url" in msg
