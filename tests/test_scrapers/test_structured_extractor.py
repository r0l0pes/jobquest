"""Tests for StructuredExtractor adapter."""

import pytest
from modules.scrapers.sources.structured_extractor import StructuredExtractor


class TestStructuredExtractorInterface:
    """Interface contract tests."""

    def test_can_resolve_returns_false(self):
        """StructuredExtractor never resolves URLs directly (decorator only)."""
        extractor = StructuredExtractor()
        assert extractor.can_resolve("https://example.com/job") is False
        assert extractor.can_resolve("https://boards.greenhouse.io/acme/jobs/1") is False

    def test_fetch_raises_not_implemented(self):
        """Fetch raises NotImplementedError — use enrich() instead."""
        extractor = StructuredExtractor()
        with pytest.raises(NotImplementedError, match="decorator"):
            extractor.fetch("https://example.com/job")

    def test_priority_is_high(self):
        """Priority is 999 (only used as post-processor, never for resolution)."""
        extractor = StructuredExtractor()
        assert extractor.priority == 999


class TestStructuredExtractorEnrich:
    """Enrichment behavior tests."""

    def _make_job(self, description: str = "") -> dict:
        """Helper: create a minimal valid job dict."""
        return {
            "title": "Product Manager",
            "company": "Acme Corp",
            "description": description,
            "url": "https://jobs.example.com/1",
            "source": "test",
            "questions": [],
        }

    def test_enrich_short_description_passes_through(self):
        """Description under 100 chars — no extraction attempted, fields pass through."""
        extractor = StructuredExtractor()
        job = self._make_job("Short description here")
        result = extractor.enrich(job)
        # All original fields preserved
        assert result["title"] == job["title"]
        assert result["company"] == job["company"]
        assert result["description"] == "Short description here"
        # No enrichment happened
        assert "required_skills" not in result

    def test_enrich_preserves_all_original_fields(self):
        """Even when enrichment fails, all original fields survive."""
        extractor = StructuredExtractor()
        job = self._make_job("A" * 200)
        result = extractor.enrich(job)
        assert result["title"] == "Product Manager"
        assert result["company"] == "Acme Corp"
        assert result["url"] == "https://jobs.example.com/1"
        assert result["source"] == "test"
        assert result["questions"] == []

    def test_enrich_returns_new_dict(self):
        """Enrich returns a copy, not a mutation of the original."""
        extractor = StructuredExtractor()
        job = self._make_job("A" * 200)
        result = extractor.enrich(job)
        assert result is not job
        # Original unmodified
        assert "required_skills" not in job

    def test_enrich_empty_description(self):
        """Empty description is handled (below 100 char threshold)."""
        extractor = StructuredExtractor()
        job = self._make_job("")
        result = extractor.enrich(job)
        assert result["description"] == ""

    def test_enrich_deep_copy_prevents_mutation(self):
        """Modifying enriched result doesn't affect original."""
        extractor = StructuredExtractor()
        job = self._make_job("A" * 200)
        result = extractor.enrich(job)
        result["title"] = "CHANGED"
        assert job["title"] == "Product Manager"
