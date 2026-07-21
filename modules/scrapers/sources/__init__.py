"""Job posting data sources — adapter registry for scraping job boards."""

from modules.scrapers.sources.registry import JobSourceRegistry

# Import scrapers to trigger auto-registration
import modules.scrapers.sources.ats_api  # noqa: F401
import modules.scrapers.sources.firecrawl  # noqa: F401
import modules.scrapers.sources.generic_html  # noqa: F401
import modules.scrapers.sources.apify_jobstream  # noqa: F401

# Import company research sources to trigger auto-registration
import modules.scrapers.sources.website_crawler  # noqa: F401
import modules.scrapers.sources.search_aggregate  # noqa: F401

__all__ = ["JobSourceRegistry"]
