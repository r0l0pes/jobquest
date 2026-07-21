"""Generic HTML adapter — last resort for unknown job board URLs."""

from modules.scrapers.sources.base import JobDataSource
from modules.scrapers.sources.registry import JobSourceRegistry


class GenericHtmlAdapter(JobDataSource):
    """Generic HTML scraping via requests + BeautifulSoup.

    This is the catch-all adapter — can_resolve returns True for ANY URL
    so it always matches when no specialized adapter does.
    """

    def can_resolve(self, url: str) -> bool:
        # Always returns True — this is the fallback adapter
        return True

    def fetch(self, url: str) -> dict:
        from modules.scrapers.job_postings import _scrape_generic

        return _scrape_generic(url)

    @property
    def priority(self) -> int:
        return 100


JobSourceRegistry.register(GenericHtmlAdapter())
