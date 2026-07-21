"""Tests for CompanyIntelligence seam and registry."""

import pytest

from modules.scrapers.sources.base import (
    CompanyIntelligence,
    CompanyIntelligenceRegistry,
)


# ── Test adapters (in-memory doubles) ──

class _MockCrawler(CompanyIntelligence):
    def can_research(self, company: str, url: str | None = None) -> bool:
        return url is not None

    @property
    def priority(self) -> int:
        return 10

    def research(
        self,
        company: str,
        url: str | None = None,
        query_types: list[str] | None = None,
    ) -> dict[str, str]:
        if not url:
            return {}
        return {"profile": f"Profile for {company} from {url}"}


class _MockSearch(CompanyIntelligence):
    def can_research(self, company: str, url: str | None = None) -> bool:
        return True

    @property
    def priority(self) -> int:
        return 50

    def research(
        self,
        company: str,
        url: str | None = None,
        query_types: list[str] | None = None,
    ) -> dict[str, str]:
        result = {}
        if query_types is None or "news" in query_types:
            result["news"] = f"News for {company}"
        if query_types is None or "profile" in query_types:
            result["profile"] = f"Search profile for {company}"
        return result


class _MockFailing(CompanyIntelligence):
    """Source that always raises."""

    def can_research(self, company: str, url: str | None = None) -> bool:
        return True

    @property
    def priority(self) -> int:
        return 5

    def research(
        self,
        company: str,
        url: str | None = None,
        query_types: list[str] | None = None,
    ) -> dict[str, str]:
        raise RuntimeError("simulated failure")


@pytest.fixture(autouse=True)
def _clear_registry():
    """Ensure registry is clean before each test."""
    CompanyIntelligenceRegistry._clear()
    yield
    CompanyIntelligenceRegistry._clear()


# ── WebsiteCrawlerSource tests ──


class TestWebsiteCrawlerSource:
    def test_can_research_with_url(self):
        source = _MockCrawler()
        assert source.can_research("Acme", "https://acme.com")

    def test_can_research_without_url(self):
        source = _MockCrawler()
        assert not source.can_research("Acme", None)

    def test_priority(self):
        source = _MockCrawler()
        assert source.priority == 10

    def test_research_returns_profile(self):
        source = _MockCrawler()
        result = source.research("Acme", "https://acme.com")
        assert "profile" in result
        assert "Acme" in result["profile"]

    def test_research_no_url_returns_empty(self):
        source = _MockCrawler()
        result = source.research("Acme", None)
        assert result == {}


# ── SearchAggregateSource tests ──


class TestSearchAggregateSource:
    def test_can_research_without_url(self):
        source = _MockSearch()
        assert source.can_research("Acme", None)

    def test_can_research_with_url(self):
        source = _MockSearch()
        assert source.can_research("Acme", "https://acme.com")

    def test_priority(self):
        source = _MockSearch()
        assert source.priority == 50

    def test_research_returns_news(self):
        source = _MockSearch()
        result = source.research("Acme", None, ["news"])
        assert "news" in result
        assert "Acme" in result["news"]

    def test_research_returns_profile_when_requested(self):
        source = _MockSearch()
        result = source.research("Acme", None, ["profile"])
        assert "profile" in result

    def test_research_returns_both_by_default(self):
        source = _MockSearch()
        result = source.research("Acme", None)
        assert "profile" in result
        assert "news" in result


# ── Registry tests ──


class TestCompanyIntelligenceRegistry:
    def test_register_adds_source(self):
        CompanyIntelligenceRegistry.register(_MockSearch())
        assert len(CompanyIntelligenceRegistry._sources) == 1

    def test_register_sorts_by_priority(self):
        CompanyIntelligenceRegistry.register(_MockSearch())  # priority 50
        CompanyIntelligenceRegistry.register(_MockCrawler())  # priority 10
        # Lower priority = earlier in list
        assert CompanyIntelligenceRegistry._sources[0].priority == 10
        assert CompanyIntelligenceRegistry._sources[1].priority == 50

    def test_research_merges_sources(self):
        CompanyIntelligenceRegistry.register(_MockSearch())
        CompanyIntelligenceRegistry.register(_MockCrawler())
        result = CompanyIntelligenceRegistry.research("Acme", "https://acme.com")
        assert "profile" in result
        assert "news" in result

    def test_research_no_duplicate_keys(self):
        """Higher-priority source wins on duplicate keys."""
        CompanyIntelligenceRegistry.register(_MockSearch())  # priority 50
        CompanyIntelligenceRegistry.register(_MockCrawler())  # priority 10
        result = CompanyIntelligenceRegistry.research("Acme", "https://acme.com")
        # Crawler (priority 10) runs first, so "profile" comes from it
        assert "Profile for Acme from https://acme.com" in result["profile"]

    def test_research_returns_empty_when_no_sources(self):
        result = CompanyIntelligenceRegistry.research("Acme")
        assert result == {}

    def test_research_returns_empty_when_no_sources_match(self):
        CompanyIntelligenceRegistry.register(_MockCrawler())  # only works with URL
        result = CompanyIntelligenceRegistry.research("Acme", None)
        # Crawler.can_research returns False without URL
        assert result == {}

    def test_research_survives_failing_source(self):
        CompanyIntelligenceRegistry.register(_MockFailing())
        CompanyIntelligenceRegistry.register(_MockSearch())
        result = CompanyIntelligenceRegistry.research("Acme")
        # Failing source raises but is caught; Search still works
        assert "profile" in result
        assert "news" in result

    def test_research_default_query_types(self):
        CompanyIntelligenceRegistry.register(_MockSearch())
        result = CompanyIntelligenceRegistry.research("Acme")
        # Default query_types = ["profile", "news"]
        assert "profile" in result
        assert "news" in result

    def test_research_explicit_query_types(self):
        CompanyIntelligenceRegistry.register(_MockSearch())
        result = CompanyIntelligenceRegistry.research("Acme", query_types=["news"])
        assert "news" in result

    def test_clear_removes_all_sources(self):
        CompanyIntelligenceRegistry.register(_MockSearch())
        CompanyIntelligenceRegistry._clear()
        assert len(CompanyIntelligenceRegistry._sources) == 0
