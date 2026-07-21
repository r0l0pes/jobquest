"""Website crawler source for company research.

Discovers and fetches important pages from a company's website
(about, solutions, case studies, etc.) to build a profile section.

Priority: 10 (primary when URL is available, crawls the actual site).
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from modules.scrapers.sources.base import CompanyIntelligence, CompanyIntelligenceRegistry


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Paths that typically contain useful company profile content
IMPORTANT_PATHS = [
    "/about", "/about-us", "/company", "/our-story", "/who-we-are",
    "/team", "/our-team", "/leadership", "/solutions", "/products",
    "/platform", "/features", "/case-studies", "/customers",
    "/insights", "/blog", "/resources", "/news", "/press",
]


class WebsiteCrawlerSource(CompanyIntelligence):
    """Fetches and extracts profile content from a company's own website.

    Discovers important pages via navigation links, then fetches
    and extracts text content for the "profile" query type.
    """

    def can_research(self, company: str, url: str | None = None) -> bool:
        """Only available when a URL is provided."""
        return url is not None

    @property
    def priority(self) -> int:
        return 10  # Primary source when URL is available

    def research(
        self,
        company: str,
        url: str | None = None,
        query_types: list[str] | None = None,
    ) -> dict[str, str]:
        if not url:
            return {}

        result: dict[str, str] = {}
        pages = self._discover_pages(url)

        # Fetch important pages for profile
        if query_types is None or "profile" in query_types:
            profile_parts: list[str] = []
            for page_url in pages[:3]:
                text = self._fetch_text(page_url)
                if text:
                    section = page_url.rstrip("/").split("/")[-1] or "Homepage"
                    section = section.replace("-", " ").replace("_", " ").title()
                    profile_parts.append(
                        f"## {section}\nSource: {page_url}\n\n{text[:2500]}"
                    )
            if profile_parts:
                result["profile"] = "\n\n".join(profile_parts)

        return result

    def _discover_pages(self, base_url: str) -> list[str]:
        """Discover important pages from the homepage navigation."""
        pages = [base_url]
        try:
            resp = requests.get(base_url, headers=_HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for nav in soup.find_all(["nav", "header"]):
                for a in nav.find_all("a", href=True):
                    href = str(a.get("href", ""))
                    if not href:
                        continue
                    for path in IMPORTANT_PATHS:
                        if path in href.lower():
                            full = urljoin(base_url, str(href))
                            if urlparse(full).netloc == urlparse(base_url).netloc:
                                if full not in pages:
                                    pages.append(full)
                                    if len(pages) >= 5:
                                        return pages
        except Exception:
            pass
        return pages[:3]

    def _fetch_text(self, url: str) -> str:
        """Fetch and extract clean text from a page."""
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            text = " ".join(text.split())
            return text if len(text) > 100 else ""
        except Exception:
            return ""


# Auto-register on import
CompanyIntelligenceRegistry.register(WebsiteCrawlerSource())
