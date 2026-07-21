"""Protocol for job posting data sources."""

from abc import ABC, abstractmethod
from typing import Optional


class JobDataSource(ABC):
    """Protocol for a job posting data source.

    Each adapter declares what URLs it can handle (can_resolve)
    and provides a fetch() that returns a structured job posting dict.
    """

    @abstractmethod
    def can_resolve(self, url: str) -> bool:
        """Return True if this adapter can handle the given URL."""
        ...

    @abstractmethod
    def fetch(self, url: str) -> dict:
        """Fetch and return a job posting dict.

        Returns:
            dict with keys: title, company, description, url, source, questions
        """
        ...

    @property
    @abstractmethod
    def priority(self) -> int:
        """Lower number = higher priority.

        Convention:
            ATS APIs (direct): 10
            Structured APIs (Apify, etc.): 20
            Stealth browsers (agent-browser): 30
            AI extractors (Firecrawl): 50
            Generic HTML: 100
            Playwright (last resort): 200
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable name for logging."""
        return self.__class__.__name__


class CompanyIntelligence(ABC):
    """Protocol for a company research data source.

    Each adapter declares what companies it can research (can_research)
    and provides a research() that returns structured sections keyed by
    query_type ("profile", "news", "tech_stack", "funding").
    """

    @abstractmethod
    def can_research(self, company: str, url: str | None = None) -> bool:
        """Return True if this source can research the given company."""
        ...

    @abstractmethod
    def research(
        self,
        company: str,
        url: str | None = None,
        query_types: list[str] | None = None,
    ) -> dict[str, str]:
        """Research a company and return structured sections.

        Returns:
            dict like {"profile": "...", "news": "..."}
            Each key is a query_type, value is text content.
        """
        ...

    @property
    @abstractmethod
    def priority(self) -> int:
        """Lower number = higher priority.

        Convention:
            Website crawlers (direct): 10
            Search aggregators: 50
            Structured APIs (Crunchbase, etc.): 40
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable name for logging."""
        return self.__class__.__name__


class CompanyIntelligenceRegistry:
    """Registry of CompanyIntelligence sources, sorted by priority.

    Sources self-register at import time via register().
    research() merges results from all matching sources.
    """

    _sources: list[CompanyIntelligence] = []

    @classmethod
    def register(cls, source: CompanyIntelligence) -> None:
        """Register a source and re-sort by priority."""
        cls._sources.append(source)
        cls._sources.sort(key=lambda s: s.priority)

    @classmethod
    def _clear(cls) -> None:
        """Clear all registered sources (for testing only)."""
        cls._sources.clear()

    @classmethod
    def research(
        cls,
        company: str,
        url: str | None = None,
        query_types: list[str] | None = None,
    ) -> dict[str, str]:
        """Research a company using all available sources.

        Merges results from all matching sources. Lower-priority sources
        only fill gaps not already covered by higher-priority ones.

        Args:
            company: Company name to research.
            url: Optional company website URL.
            query_types: List of intelligence types ("profile", "news", etc.).
                Defaults to ["profile", "news"].

        Returns:
            dict mapping query_type to text content. Empty dict if no
            sources matched or all failed.
        """
        if query_types is None:
            query_types = ["profile", "news"]

        result: dict[str, str] = {}
        for source in cls._sources:
            try:
                if source.can_research(company, url):
                    sections = source.research(company, url, query_types)
                    for key, value in sections.items():
                        if value and key not in result:
                            result[key] = value
            except Exception:
                continue

        return result
