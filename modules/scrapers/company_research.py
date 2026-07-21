"""Company research module for the job scraper.
Extracted from job_scraper.py — handles company page discovery,
multi-strategy page fetching, and search."""

import os
import re
import json

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from rich.console import Console

# Firecrawl API for enhanced web scraping (handles anti-bot, JS rendering)
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ─── Company Research ─────────────────────────────────────────────


def _discover_important_pages(base_url: str) -> list[str]:
    """Discover important pages on a company website for research.

    Companies use different names for similar content. We look for all variations.
    """
    # Comprehensive list of paths - companies use different naming conventions
    important_paths = [
        # About / Company
        "/about", "/about-us", "/company", "/our-story", "/who-we-are",
        "/team", "/our-team", "/leadership", "/our-mission",
        # Products / Solutions / Services
        "/solutions", "/products", "/services", "/platform", "/offerings",
        "/what-we-do", "/our-work", "/features", "/capabilities",
        # Case Studies / Clients / Success
        "/case-studies", "/case-study", "/customers", "/success-stories",
        "/clients", "/portfolio", "/our-impact", "/results", "/testimonials",
        "/partners", "/trusted-by",
        # Industries / Use Cases
        "/industries", "/sectors", "/use-cases", "/for-banks", "/for-enterprise",
        # Insights / News / Blog
        "/insights", "/blog", "/resources", "/news", "/press",
        "/updates", "/announcements", "/articles",
        # Why Us / How it Works
        "/why-us", "/why-choose-us", "/how-it-works", "/our-approach",
    ]

    pages = [base_url]  # Always include homepage

    # Try to fetch homepage and find links
    try:
        resp = requests.get(base_url, headers=_HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find links in navigation
        for nav in soup.find_all(["nav", "header"]):
            for a in nav.find_all("a", href=True):
                href = a["href"]
                # Check if it matches important paths
                for path in important_paths:
                    if path in href.lower():
                        full_url = urljoin(base_url, href)
                        # Only add if same domain
                        if urlparse(full_url).netloc == urlparse(base_url).netloc:
                            if full_url not in pages:
                                pages.append(full_url)
                                if len(pages) >= 5:  # Limit to 5 pages
                                    return pages
    except Exception:
        pass

    # Fallback: try common paths directly
    if len(pages) < 3:
        for path in ["/about", "/solutions", "/case-studies", "/customers"]:
            try:
                test_url = urljoin(base_url, path)
                resp = requests.head(test_url, headers=_HEADERS, timeout=5, allow_redirects=True)
                if resp.status_code == 200 and test_url not in pages:
                    pages.append(test_url)
                    if len(pages) >= 5:
                        break
            except Exception:
                continue

    return pages


def _fetch_company_pages_crawl4ai(pages: list[str], log) -> list[str]:
    """Fetch pages using crawl4ai — handles JS-heavy SPAs better than plain Playwright.

    Falls back to per-page async crawl. Free, no API key required.
    """
    import asyncio

    async def _crawl(urls):
        from crawl4ai import AsyncWebCrawler
        results = []
        async with AsyncWebCrawler(headless=True) as crawler:
            for url in urls:
                try:
                    result = await crawler.arun(url=url)
                    text = result.markdown or result.cleaned_html or ""
                    if len(text) > 200:
                        section = url.rstrip("/").split("/")[-1] or "Homepage"
                        section = section.replace("-", " ").replace("_", " ").title()
                        results.append(f"## {section}\nSource: {url}\n\n{text[:2500]}")
                        log(f"  [dim]✓ crawl4ai: {section}[/dim]")
                except Exception:
                    continue
        return results

    try:
        return asyncio.run(_crawl(pages[:5]))
    except Exception as e:
        log(f"  [yellow]crawl4ai failed: {e}[/yellow]")
        return []


def _fetch_company_pages_playwright(pages: list[str], log) -> list[str]:
    """Fetch multiple company pages using a single Playwright browser instance.

    Returns list of text strings, one per successfully fetched page.
    """
    from playwright.sync_api import sync_playwright

    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for url in pages[:5]:
                try:
                    pg = browser.new_page()
                    pg.goto(url, wait_until="domcontentloaded", timeout=20000)
                    # Extra wait for JS-heavy SPAs to render page-specific content
                    pg.wait_for_timeout(2500)
                    html = pg.content()
                    pg.close()

                    soup = BeautifulSoup(html, "html.parser")
                    # Strip boilerplate
                    for tag in soup(["script", "style", "nav", "header", "footer",
                                     "aside", "form", "noscript"]):
                        tag.decompose()

                    text = soup.get_text(separator=" ", strip=True)
                    # Collapse whitespace
                    text = " ".join(text.split())

                    if len(text) > 200:
                        section = url.rstrip("/").split("/")[-1] or "Homepage"
                        section = section.replace("-", " ").replace("_", " ").title()
                        results.append(f"## {section}\nSource: {url}\n\n{text[:2500]}")
                        log(f"  [dim]✓ Playwright: {section}[/dim]")
                except Exception:
                    continue
            browser.close()
    except Exception as e:
        log(f"  [yellow]Playwright company research failed: {e}[/yellow]")

    return results


def research_company(
    company_name: str, company_url: str | None = None, console: Console | None = None
) -> str:
    """Research a company comprehensively for cover letter writing.

    Fetches multiple pages: homepage, about, solutions, case studies, etc.
    Returns company information as text for LLM context.

    Scraping order (cheapest first):
      1. Playwright — free, renders JS, one browser instance for all pages
      2. Firecrawl  — paid, better markdown; only if Playwright yields thin content
      3. Plain HTML — last resort single-page fetch
      4. Web search — when no company URL is provided
    """
    log = console.print if console else print
    log(f"  [dim]Researching {company_name}...[/dim]")

    # Try the CompanyIntelligenceRegistry first (new seam).
    # Sources self-register on import — website crawlers first (priority 10),
    # then search aggregators (priority 50). The registry merges results
    # across all matching sources, with lower-priority sources only filling
    # gaps not already covered.
    try:
        from modules.scrapers.sources.base import CompanyIntelligenceRegistry
        sections = CompanyIntelligenceRegistry.research(
            company_name, company_url, query_types=["profile", "news"]
        )
        if sections:
            result_parts = []
            if "profile" in sections and sections["profile"]:
                result_parts.append(f"## Company Profile\n\n{sections['profile']}")
            if "news" in sections and sections["news"]:
                result_parts.append(f"## Recent News\n\n{sections['news']}")
            if result_parts:
                text = "\n\n---\n\n".join(result_parts)
                log(f"  [green]✓ Registry research: {len(sections)} queries matched[/green]")
                return text
    except Exception as e:
        log(f"  [dim]Registry unavailable ({e}), falling back to legacy path[/dim]")

    results_text = []

    if company_url:
        pages_to_fetch = _discover_important_pages(company_url)
        log(f"  [dim]Found {len(pages_to_fetch)} pages to research[/dim]")

        # Strategy 1: Playwright (free, JS-rendering)
        results_text = _fetch_company_pages_playwright(pages_to_fetch, log)
        if results_text:
            total_chars = sum(len(r) for r in results_text)
            log(f"  [green]✓ Playwright research: {len(results_text)} pages, {total_chars} chars[/green]")

        # Detect SPA trap: all pages labelled "Homepage" means Playwright got the same
        # shell page for every URL (React/Next.js SPA that requires JS routing).
        all_homepage = results_text and all("## Homepage" in r for r in results_text)
        playwright_thin = not results_text or all_homepage

        # Strategy 1b: crawl4ai if Playwright was thin (SPA or no content)
        if playwright_thin:
            log(f"  [dim]Playwright thin/SPA — trying crawl4ai[/dim]")
            results_text = _fetch_company_pages_crawl4ai(pages_to_fetch, log)
            if results_text:
                total_chars = sum(len(r) for r in results_text)
                log(f"  [green]✓ crawl4ai research: {len(results_text)} pages, {total_chars} chars[/green]")

        # Strategy 2: Firecrawl if still thin
        if not results_text and FIRECRAWL_API_KEY:
            log(f"  [dim]Playwright thin — trying Firecrawl: {company_url}[/dim]")
            try:
                from firecrawl import FirecrawlApp
                app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
                for page_url in pages_to_fetch[:5]:
                    try:
                        doc = app.scrape(page_url, formats=["markdown"], wait_for=2000)
                        markdown = doc.markdown or ""
                        if markdown and len(markdown) > 100:
                            section = page_url.rstrip("/").split("/")[-1] or "Homepage"
                            section = section.replace("-", " ").replace("_", " ").title()
                            results_text.append(f"## {section}\nSource: {page_url}\n\n{markdown[:2500]}")
                            log(f"  [dim]✓ Firecrawl: {section}[/dim]")
                    except Exception:
                        continue
                if results_text:
                    log(f"  [green]✓ Firecrawl research: {len(results_text)} pages[/green]")
            except Exception as e:
                log(f"  [yellow]Firecrawl failed: {e}[/yellow]")

        # Strategy 3: Plain HTML single-page fallback
        if not results_text:
            try:
                direct_info = _fetch_company_page(company_url)
                if direct_info:
                    results_text.append(f"Source: {company_url}\n\n{direct_info}")
                    log("  [dim]✓ Plain HTML fetch[/dim]")
            except Exception as e:
                log(f"  [yellow]Could not fetch company URL: {e}[/yellow]")

    # Strategy 4: Search (no URL provided, or all fetches failed)
    if not results_text:
        queries = [
            f"{company_name} recent news product launches 2025 2026",
            f"{company_name} product features latest",
        ]

        # Try Google first
        search_results = _search_google(queries)
        if search_results:
            log("  [dim]Found research via Google[/dim]")
            results_text.append(search_results)
        else:
            # Fallback to DuckDuckGo
            log("  [dim]Google unavailable, using DuckDuckGo...[/dim]")
            search_results = _search_duckduckgo(queries)
            if search_results:
                results_text.append(search_results)

    if not results_text:
        log("  [yellow]No research results found.[/yellow]")
        return ""

    return "\n\n---\n\n".join(results_text)


def _fetch_company_page(url: str) -> str:
    """Fetch and extract key info from company website.
    Uses Firecrawl if available for better JS handling.
    """
    # Try Firecrawl first for better results
    if FIRECRAWL_API_KEY:
        try:
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
            doc = app.scrape(url, formats=["markdown"], wait_for=2000)
            markdown = doc.markdown or ""
            if markdown and len(markdown) > 100:
                # Truncate to reasonable size for company research
                return markdown[:3000]
        except Exception:
            pass  # Fall through to regular fetch

    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    info_parts = []

    # Get meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        info_parts.append(f"About: {meta['content']}")

    # Get og:description
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc and og_desc.get("content") and og_desc["content"] not in str(info_parts):
        info_parts.append(f"Description: {og_desc['content']}")

    # Get main headings and their following paragraphs
    for h in soup.find_all(["h1", "h2"], limit=5):
        heading = h.get_text(strip=True)
        if len(heading) > 5 and len(heading) < 100:
            # Get following paragraph
            next_p = h.find_next("p")
            if next_p:
                para = next_p.get_text(strip=True)[:300]
                if para:
                    info_parts.append(f"{heading}: {para}")

    # Get first few paragraphs from main content
    main = soup.find("main") or soup.find("article") or soup.find("body")
    if main:
        for p in main.find_all("p", limit=5):
            text = p.get_text(strip=True)
            if len(text) > 50 and text not in str(info_parts):
                info_parts.append(text[:400])

    return "\n\n".join(info_parts[:8]) if info_parts else ""


def _search_google(queries: list[str]) -> str:
    """Search via googlesearch-python (no API key needed)."""
    try:
        from googlesearch import search as gsearch
    except ImportError:
        return ""

    results_text = []
    for query in queries:
        try:
            for url in gsearch(query, num_results=3, lang="en"):
                results_text.append(f"URL: {url}")
        except Exception:
            continue

    # Google only returns URLs, so fetch snippets from each
    for url in results_text[:4]:
        url_str = url.replace("URL: ", "")
        try:
            resp = requests.get(
                url_str, headers=_HEADERS, timeout=10
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            # Get meta description or first paragraphs
            meta = soup.find("meta", attrs={"name": "description"})
            if meta and meta.get("content"):
                results_text.append(
                    f"Source: {url_str}\nSnippet: {meta['content']}"
                )
            else:
                paras = soup.find_all("p", limit=3)
                text = " ".join(p.get_text(strip=True) for p in paras)
                if text:
                    results_text.append(
                        f"Source: {url_str}\nSnippet: {text[:500]}"
                    )
        except Exception:
            continue

    return "\n\n---\n\n".join(results_text) if results_text else ""


def _search_duckduckgo(queries: list[str]) -> str:
    """Search via duckduckgo-search (already a project dependency)."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return ""

    results_text = []
    ddgs = DDGS()

    for query in queries:
        try:
            results = list(ddgs.text(query, max_results=3))
            for r in results:
                results_text.append(
                    f"Title: {r['title']}\n"
                    f"Snippet: {r['body']}\n"
                    f"URL: {r['href']}"
                )
        except Exception:
            continue

    return "\n\n---\n\n".join(results_text) if results_text else ""
