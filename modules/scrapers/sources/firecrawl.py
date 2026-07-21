"""Firecrawl adapter for AI-enhanced job posting scraping."""

import os

from modules.scrapers.sources.base import JobDataSource
from modules.scrapers.sources.registry import JobSourceRegistry


class FirecrawlAdapter(JobDataSource):
    """Firecrawl API adapter for JS-heavy and anti-bot-protected pages.

    Only resolves when FIRECRAWL_API_KEY is configured.
    Falls back to generic scraping for URL pattern matching.
    """

    def can_resolve(self, url: str) -> bool:
        return bool(os.getenv("FIRECRAWL_API_KEY", ""))

    def fetch(self, url: str) -> dict:
        from modules.scrapers.job_postings import _scrape_with_firecrawl

        return _scrape_with_firecrawl(url)

    @property
    def priority(self) -> int:
        return 50


JobSourceRegistry.register(FirecrawlAdapter())
