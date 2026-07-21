"""Tests for JobSourceRegistry — adapter registration and resolution."""

import pytest

from modules.scrapers.sources.base import JobDataSource
from modules.scrapers.sources.registry import JobSourceRegistry


class _FakeAdapter(JobDataSource):
    """Test adapter that matches URLs containing a specific substring."""

    def __init__(self, match_substring: str, result_title: str, priority: int = 50):
        self._match = match_substring
        self._title = result_title
        self._priority = priority

    def can_resolve(self, url: str) -> bool:
        return self._match in url

    def fetch(self, url: str) -> dict:
        return {
            "title": self._title,
            "company": "",
            "description": f"Fetched from {url}",
            "url": url,
            "source": "test",
            "questions": [],
        }

    @property
    def priority(self) -> int:
        return self._priority


class TestJobSourceRegistry:
    """Tests for the adapter registry."""

    def teardown_method(self):
        """Clean up after each test."""
        JobSourceRegistry._clear()

    def test_register_adds_adapter(self):
        """Registering an adapter adds it to the list."""
        before = len(JobSourceRegistry._adapters)
        adapter = _FakeAdapter("test", "Test Job")
        JobSourceRegistry.register(adapter)
        assert len(JobSourceRegistry._adapters) == before + 1

    def test_register_sorts_by_priority(self):
        """Adapters are sorted by priority (lower = first)."""
        a1 = _FakeAdapter("z", "Last", priority=100)
        a2 = _FakeAdapter("a", "First", priority=10)
        a3 = _FakeAdapter("m", "Middle", priority=50)

        JobSourceRegistry.register(a1)
        JobSourceRegistry.register(a2)
        JobSourceRegistry.register(a3)

        priorities = [a.priority for a in JobSourceRegistry._adapters]
        assert priorities == [10, 50, 100]

    def test_resolve_returns_correct_adapter(self):
        """resolve() returns the first adapter whose can_resolve is True."""
        a1 = _FakeAdapter("greenhouse", "GH Job", priority=10)
        a2 = _FakeAdapter("lever", "Lever Job", priority=10)

        JobSourceRegistry.register(a1)
        JobSourceRegistry.register(a2)

        result = JobSourceRegistry.resolve("https://jobs.lever.co/company/123")
        assert result is not None
        assert result._title == "Lever Job"

    def test_resolve_returns_none_for_unmatched_url(self):
        """resolve() returns None when no adapter matches."""
        a1 = _FakeAdapter("greenhouse", "GH Job")
        JobSourceRegistry.register(a1)

        result = JobSourceRegistry.resolve("https://unknown.example.com/job")
        assert result is None

    def test_fetch_delegates_to_adapter(self):
        """fetch() resolves and delegates to the matching adapter."""
        a1 = _FakeAdapter("example", "Delegated Job")
        JobSourceRegistry.register(a1)

        result = JobSourceRegistry.fetch("https://www.example.com/jobs/1")
        assert result["title"] == "Delegated Job"
        assert result["source"] == "test"
        assert result["url"] == "https://www.example.com/jobs/1"

    def test_fetch_returns_empty_result_for_unresolved(self):
        """fetch() returns an empty dict with 'unresolved' source for unknown URLs."""
        result = JobSourceRegistry.fetch("https://unknown.example.com/job")
        assert result["title"] == ""
        assert result["source"] == "unresolved"
        assert result["url"] == "https://unknown.example.com/job"

    def test_duplicate_priorities_preserve_registration_order(self):
        """Adapters with same priority keep insertion order (stable sort)."""
        a1 = _FakeAdapter("first", "First", priority=50)
        a2 = _FakeAdapter("second", "Second", priority=50)

        JobSourceRegistry.register(a1)
        JobSourceRegistry.register(a2)

        titles = [a._title for a in JobSourceRegistry._adapters]
        assert titles == ["First", "Second"]

    def test_resolve_uses_highest_priority_first(self):
        """When multiple adapters match, highest priority (lowest number) wins."""
        a1 = _FakeAdapter("job", "Generic Match", priority=100)
        a2 = _FakeAdapter("example.com", "Specific Match", priority=10)

        JobSourceRegistry.register(a1)
        JobSourceRegistry.register(a2)

        result = JobSourceRegistry.resolve("https://www.example.com/job")
        assert result is not None
        assert result._title == "Specific Match"
