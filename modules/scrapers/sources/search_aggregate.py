"""Search aggregator source for company research.

Uses DuckDuckGo (already a project dependency) to find news,
product announcements, and company overviews from the web.

Priority: 50 (secondary — always available, but less specific than
direct website crawling).
"""

from modules.scrapers.sources.base import CompanyIntelligence, CompanyIntelligenceRegistry


class SearchAggregateSource(CompanyIntelligence):
    """Searches the web for company news and profile information.

    Always available as a fallback. Uses DuckDuckGo for search
    (no API key required; already a project dependency via
    duckduckgo-search package).
    """

    def can_research(self, company: str, url: str | None = None) -> bool:
        """Always available — works with or without a URL."""
        return True

    @property
    def priority(self) -> int:
        return 50  # Secondary source

    def research(
        self,
        company: str,
        url: str | None = None,
        query_types: list[str] | None = None,
    ) -> dict[str, str]:
        result: dict[str, str] = {}

        # News query type: recent news, product launches
        if query_types is None or "news" in query_types:
            news_queries = [
                f"{company} recent news product launches",
                f"{company} product features latest",
            ]
            news_text = self._search(news_queries)
            if news_text:
                result["news"] = news_text

        # Profile query type: company overview from web
        if query_types is None or "profile" in query_types:
            profile_queries = [
                f"{company} about company overview",
            ]
            profile_text = self._search(profile_queries)
            if profile_text and "profile" not in result:
                result["profile"] = profile_text

        return result

    def _search(self, queries: list[str]) -> str:
        """Search DuckDuckGo and return formatted results.

        Returns empty string if duckduckgo-search is not installed
        or all queries fail.
        """
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return ""

        ddgs = DDGS()
        results_text: list[str] = []

        for query in queries:
            try:
                results = list(ddgs.text(query, max_results=3))
                for r in results:
                    title = r.get("title", "")
                    body = r.get("body", "")
                    href = r.get("href", "")
                    results_text.append(
                        f"Title: {title}\nSnippet: {body}\nURL: {href}"
                    )
            except Exception:
                continue

        if results_text:
            return "\n\n".join(results_text[:6])
        return ""


# Auto-register on import
CompanyIntelligenceRegistry.register(SearchAggregateSource())
