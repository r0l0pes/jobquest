"""Tests for ATS API adapters — URL pattern matching and priority ordering."""

import pytest

from modules.scrapers.sources.ats_api import (
    GreenhouseAdapter,
    LeverAdapter,
    AshbyAdapter,
    WorkableAdapter,
    PersonioAdapter,
    ScreenloopAdapter,
)
from modules.scrapers.sources.firecrawl import FirecrawlAdapter
from modules.scrapers.sources.generic_html import GenericHtmlAdapter


class TestGreenhouseAdapter:
    """Greenhouse URL pattern matching."""

    def test_can_resolve_positive(self):
        adapter = GreenhouseAdapter()
        assert adapter.can_resolve(
            "https://boards.greenhouse.io/company/jobs/12345"
        )
        assert adapter.can_resolve(
            "https://job-boards.eu.greenhouse.io/company/jobs/67890"
        )

    def test_can_resolve_negative(self):
        adapter = GreenhouseAdapter()
        assert not adapter.can_resolve("https://jobs.lever.co/company/123")
        assert not adapter.can_resolve("https://www.google.com")

    def test_priority(self):
        assert GreenhouseAdapter().priority == 10


class TestLeverAdapter:
    """Lever URL pattern matching."""

    def test_can_resolve_positive(self):
        adapter = LeverAdapter()
        assert adapter.can_resolve(
            "https://jobs.lever.co/company/abc-def-123"
        )

    def test_can_resolve_negative(self):
        adapter = LeverAdapter()
        assert not adapter.can_resolve(
            "https://boards.greenhouse.io/company/jobs/1"
        )

    def test_priority(self):
        assert LeverAdapter().priority == 10


class TestAshbyAdapter:
    """Ashby URL pattern matching."""

    def test_can_resolve_positive(self):
        adapter = AshbyAdapter()
        assert adapter.can_resolve(
            "https://jobs.ashbyhq.com/company/senior-pm"
        )
        assert adapter.can_resolve(
            "https://jobs.ashbyhq.com/company"
        )

    def test_can_resolve_negative(self):
        adapter = AshbyAdapter()
        assert not adapter.can_resolve("https://jobs.lever.co/company/123")

    def test_priority(self):
        assert AshbyAdapter().priority == 10


class TestWorkableAdapter:
    """Workable URL pattern matching."""

    def test_can_resolve_positive(self):
        adapter = WorkableAdapter()
        assert adapter.can_resolve(
            "https://apply.workable.com/company/j/slug123"
        )

    def test_can_resolve_negative(self):
        adapter = WorkableAdapter()
        assert not adapter.can_resolve("https://boards.greenhouse.io/co/jobs/1")

    def test_priority(self):
        assert WorkableAdapter().priority == 10


class TestPersonioAdapter:
    """Personio URL pattern matching."""

    def test_can_resolve_positive(self):
        adapter = PersonioAdapter()
        assert adapter.can_resolve(
            "https://company.jobs.personio.de/job/12345"
        )
        assert adapter.can_resolve(
            "https://company.jobs.personio.com/job/67890"
        )

    def test_can_resolve_negative(self):
        adapter = PersonioAdapter()
        assert not adapter.can_resolve("https://jobs.lever.co/company/123")

    def test_priority(self):
        assert PersonioAdapter().priority == 10


class TestScreenloopAdapter:
    """Screenloop URL pattern matching."""

    def test_can_resolve_positive(self):
        adapter = ScreenloopAdapter()
        assert adapter.can_resolve(
            "https://app.screenloop.com/careers/company/job_posts/12345"
        )

    def test_can_resolve_negative(self):
        adapter = ScreenloopAdapter()
        assert not adapter.can_resolve("https://boards.greenhouse.io/co/jobs/1")

    def test_priority(self):
        assert ScreenloopAdapter().priority == 10


class TestPriorityOrdering:
    """Verify priority conventions: ATS < Firecrawl < generic."""

    def test_ats_before_firecrawl(self):
        assert GreenhouseAdapter().priority < FirecrawlAdapter().priority

    def test_firecrawl_before_generic(self):
        assert FirecrawlAdapter().priority < GenericHtmlAdapter().priority

    def test_all_ats_same_priority(self):
        adapters = [
            GreenhouseAdapter(),
            LeverAdapter(),
            AshbyAdapter(),
            WorkableAdapter(),
            PersonioAdapter(),
            ScreenloopAdapter(),
        ]
        for a in adapters:
            assert a.priority == 10, f"{a.name} should have priority 10"


class TestGenericHtmlAdapter:
    """Generic HTML adapter — always resolves."""

    def test_can_resolve_always_true(self):
        adapter = GenericHtmlAdapter()
        assert adapter.can_resolve("https://any.url.com/whatever")
        assert adapter.can_resolve("")
        assert adapter.can_resolve("not-even-a-url")

    def test_priority_is_last(self):
        adapter = GenericHtmlAdapter()
        assert adapter.priority == 100
