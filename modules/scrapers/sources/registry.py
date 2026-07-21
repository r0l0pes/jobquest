"""Adapter registry for job posting data sources.

Adapters self-register on import. The registry resolves URLs to the
highest-priority matching adapter.
"""

from typing import Optional

from modules.scrapers.sources.base import JobDataSource


class JobSourceRegistry:
    """Registry of JobDataSource adapters, sorted by priority.

    Adapters register themselves at import time via register().
    resolve() returns the first adapter whose can_resolve() returns True.
    """

    _adapters: list[JobDataSource] = []

    @classmethod
    def register(cls, adapter: JobDataSource) -> None:
        """Register an adapter and re-sort by priority."""
        cls._adapters.append(adapter)
        cls._adapters.sort(key=lambda a: a.priority)

    @classmethod
    def resolve(cls, url: str) -> Optional[JobDataSource]:
        """Return the first adapter that can handle the URL, or None."""
        for adapter in cls._adapters:
            if adapter.can_resolve(url):
                return adapter
        return None

    @classmethod
    def fetch(cls, url: str) -> dict:
        """Resolve and fetch — convenience method.

        Returns:
            Job posting dict or an empty result with source="unresolved".
        """
        adapter = cls.resolve(url)
        if adapter is None:
            return {
                "title": "",
                "company": "",
                "description": "",
                "url": url,
                "source": "unresolved",
                "questions": [],
            }
        return adapter.fetch(url)

    @classmethod
    def _clear(cls) -> None:
        """Clear all registered adapters (for testing only)."""
        cls._adapters.clear()
