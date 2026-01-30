"""Job posting scraper and company research module.

Supports structured APIs for Greenhouse, Lever, Ashby, and Workable.
Falls back to generic HTML scraping, then Playwright for JS-heavy pages.
Company research via Google (primary) with DuckDuckGo fallback.
"""

import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from rich.console import Console


# ─── ATS URL Patterns ────────────────────────────────────────────

# Greenhouse: boards.greenhouse.io/{board}/jobs/{id}
_GREENHOUSE_PATTERN = re.compile(
    r"boards\.greenhouse\.io/([\w-]+)/jobs/(\d+)"
)

# Lever: jobs.lever.co/{company}/{uuid}
_LEVER_PATTERN = re.compile(
    r"jobs\.lever\.co/([\w-]+)/([\w-]+)"
)

# Ashby: jobs.ashbyhq.com/{company}/{slug}  (slug is optional for listing)
_ASHBY_PATTERN = re.compile(
    r"jobs\.ashbyhq\.com/([\w-]+)(?:/([\w-]+))?"
)

# Workable: apply.workable.com/{company}/j/{slug}
_WORKABLE_PATTERN = re.compile(
    r"apply\.workable\.com/([\w-]+)/j/([\w-]+)"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ─── Public ATS APIs ─────────────────────────────────────────────


def _scrape_greenhouse(board: str, job_id: str) -> dict:
    """Greenhouse public boards API — returns structured JSON including
    application questions.
    Docs: https://developers.greenhouse.io/job-board.html
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    content_html = data.get("content", "")
    description = BeautifulSoup(content_html, "html.parser").get_text(
        separator="\n", strip=True
    )

    questions = [
        q.get("label", "")
        for q in data.get("questions", [])
        if q.get("label")
    ]

    return {
        "title": data.get("title", ""),
        "company": data.get("company", {}).get("name", ""),
        "description": description,
        "url": data.get("absolute_url", ""),
        "source": "greenhouse_api",
        "questions": questions,
    }


def _scrape_lever(company: str, posting_id: str) -> dict:
    """Lever public postings API (v0) — no auth required.
    Docs: https://github.com/lever/postings-api
    """
    url = f"https://api.lever.co/v0/postings/{company}/{posting_id}?mode=json"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # Lever returns description as HTML and descriptionPlain
    desc_html = data.get("description", "") + "\n" + data.get(
        "additional", ""
    )
    description = BeautifulSoup(desc_html, "html.parser").get_text(
        separator="\n", strip=True
    )

    # Lever lists sections with body content
    for section in data.get("lists", []):
        description += (
            f"\n\n{section.get('text', '')}:\n"
            + BeautifulSoup(
                section.get("content", ""), "html.parser"
            ).get_text(separator="\n", strip=True)
        )

    return {
        "title": data.get("text", ""),
        "company": company.replace("-", " ").title(),
        "description": description,
        "url": data.get("hostedUrl", f"https://jobs.lever.co/{company}/{posting_id}"),
        "source": "lever_api",
        "questions": [],  # Lever doesn't expose questions in public API
    }


def _scrape_ashby(company: str, slug: str | None) -> dict:
    """Ashby public job posting API — returns all jobs for a company.
    If slug is provided, finds the matching job.
    Docs: https://developers.ashbyhq.com/docs/public-job-posting-api
    """
    api_url = f"https://jobs.ashbyhq.com/api/non-user-graphql"
    # Ashby uses a GraphQL endpoint for its public API
    payload = {
        "operationName": "ApiJobBoardWithTeams",
        "variables": {"organizationHostedJobsPageName": company},
        "query": """
            query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
                jobBoard: jobBoardWithTeams(
                    organizationHostedJobsPageName: $organizationHostedJobsPageName
                ) {
                    teams {
                        ... on JobBoardTeam {
                            jobs {
                                id
                                title
                                descriptionHtml
                                locationName
                                employmentType
                            }
                        }
                    }
                    jobBoardSetting {
                        organizationName
                    }
                }
            }
        """,
    }

    resp = requests.post(api_url, json=payload, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    board = data.get("data", {}).get("jobBoard", {})
    org_name = (
        board.get("jobBoardSetting", {}).get("organizationName", company)
    )

    # Flatten all jobs from all teams
    all_jobs = []
    for team in board.get("teams", []):
        all_jobs.extend(team.get("jobs", []))

    # Find matching job by slug (partial ID match) or return first
    job = None
    if slug:
        slug_lower = slug.lower()
        for j in all_jobs:
            if slug_lower in j.get("id", "").lower() or slug_lower in j.get(
                "title", ""
            ).lower().replace(" ", "-"):
                job = j
                break

    if not job and all_jobs:
        # If no slug match, fall back to HTML scraping
        return _scrape_generic(
            f"https://jobs.ashbyhq.com/{company}/{slug or ''}"
        )

    if not job:
        return _empty_result(f"https://jobs.ashbyhq.com/{company}/{slug or ''}")

    description = BeautifulSoup(
        job.get("descriptionHtml", ""), "html.parser"
    ).get_text(separator="\n", strip=True)

    return {
        "title": job.get("title", ""),
        "company": org_name,
        "description": description,
        "url": f"https://jobs.ashbyhq.com/{company}/{slug or ''}",
        "source": "ashby_api",
        "questions": [],
    }


def _scrape_workable(company: str, slug: str) -> dict:
    """Workable public widget API — no auth required.
    Docs: https://workable.readme.io/
    """
    # First get job list to find the matching job
    list_url = (
        f"https://apply.workable.com/api/v1/widget/accounts/{company}"
    )
    resp = requests.get(list_url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # Find matching job by shortcode (slug)
    job = None
    for j in data.get("jobs", []):
        if j.get("shortcode", "").lower() == slug.lower():
            job = j
            break
        # Also try matching by URL slug
        job_url = j.get("url", "")
        if slug.lower() in job_url.lower():
            job = j
            break

    if not job:
        # Fallback to HTML scraping if job not found in widget API
        return _scrape_generic(
            f"https://apply.workable.com/{company}/j/{slug}/"
        )

    # Fetch detailed job info
    shortcode = job.get("shortcode", slug)
    detail_url = (
        f"https://apply.workable.com/api/v1/widget/accounts/"
        f"{company}/jobs/{shortcode}"
    )
    try:
        detail_resp = requests.get(
            detail_url, headers=_HEADERS, timeout=15
        )
        detail_resp.raise_for_status()
        detail = detail_resp.json()
        description = BeautifulSoup(
            detail.get("description", ""), "html.parser"
        ).get_text(separator="\n", strip=True)

        # Workable sometimes has requirements separately
        requirements = detail.get("requirements", "")
        if requirements:
            description += "\n\nRequirements:\n" + BeautifulSoup(
                requirements, "html.parser"
            ).get_text(separator="\n", strip=True)

        benefits = detail.get("benefits", "")
        if benefits:
            description += "\n\nBenefits:\n" + BeautifulSoup(
                benefits, "html.parser"
            ).get_text(separator="\n", strip=True)

        questions = [
            q.get("label", "") or q.get("body", "")
            for q in detail.get("questions", [])
            if q.get("label") or q.get("body")
        ]
    except Exception:
        description = job.get("title", "")
        questions = []

    return {
        "title": job.get("title", ""),
        "company": data.get("name", company.replace("-", " ").title()),
        "description": description,
        "url": job.get("url", f"https://apply.workable.com/{company}/j/{slug}/"),
        "source": "workable_api",
        "questions": questions,
    }


# ─── Generic Scraping ────────────────────────────────────────────


def _scrape_generic(url: str) -> dict:
    """Generic HTML scraping via requests + BeautifulSoup."""
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    return _extract_from_html(resp.text, url)


def _scrape_with_playwright(url: str) -> dict:
    """Fallback: full browser render for JS-heavy pages."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        browser.close()
        return _extract_from_html(html, url)


def _extract_from_html(html: str, url: str) -> dict:
    """Parse HTML and extract job posting data."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Title extraction — try common selectors
    title = ""
    for selector in [
        "h1.job-title",
        "h1.posting-headline",
        "[data-qa='job-title']",
        ".job-title",
        ".posting-title",
        "h1",
    ]:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True):
            title = el.get_text(strip=True)
            break

    # Company extraction
    company = ""
    for selector in [
        ".company-name",
        "[data-qa='company-name']",
    ]:
        el = soup.select_one(selector)
        if el:
            company = el.get_text(strip=True)
            break

    if not company:
        meta = soup.select_one("meta[property='og:site_name']")
        if meta:
            company = meta.get("content", "")

    if not company:
        domain = urlparse(url).hostname or ""
        ats_domains = [
            "greenhouse",
            "lever",
            "ashby",
            "workable",
            "personio",
            "smartrecruiters",
            "bamboohr",
            "recruitee",
        ]
        if not any(ats in domain for ats in ats_domains):
            company = domain.split(".")[0].title()

    description = soup.get_text(separator="\n", strip=True)

    return {
        "title": title,
        "company": company,
        "description": description,
        "url": url,
        "source": "html",
        "questions": [],
    }


def _empty_result(url: str) -> dict:
    return {
        "title": "",
        "company": "",
        "description": "",
        "url": url,
        "source": "empty",
        "questions": [],
    }


# ─── Main Entry Point ────────────────────────────────────────────


def scrape_job_posting(
    url: str, console: Console | None = None
) -> dict:
    """Scrape a job posting URL. Tries ATS APIs first, then HTML,
    then Playwright.

    Returns dict: title, company, description, url, source, questions
    """
    log = console.print if console else print

    # Check for known ATS API patterns
    gh = _GREENHOUSE_PATTERN.search(url)
    if gh:
        log("  [dim]Greenhouse detected — using API...[/dim]")
        try:
            return _scrape_greenhouse(gh.group(1), gh.group(2))
        except Exception as e:
            log(f"  [yellow]Greenhouse API failed: {e}. Falling back to HTML.[/yellow]")

    lever = _LEVER_PATTERN.search(url)
    if lever:
        log("  [dim]Lever detected — using API...[/dim]")
        try:
            return _scrape_lever(lever.group(1), lever.group(2))
        except Exception as e:
            log(f"  [yellow]Lever API failed: {e}. Falling back to HTML.[/yellow]")

    ashby = _ASHBY_PATTERN.search(url)
    if ashby:
        log("  [dim]Ashby detected — using API...[/dim]")
        try:
            return _scrape_ashby(ashby.group(1), ashby.group(2))
        except Exception as e:
            log(f"  [yellow]Ashby API failed: {e}. Falling back to HTML.[/yellow]")

    workable = _WORKABLE_PATTERN.search(url)
    if workable:
        log("  [dim]Workable detected — using API...[/dim]")
        try:
            return _scrape_workable(workable.group(1), workable.group(2))
        except Exception as e:
            log(f"  [yellow]Workable API failed: {e}. Falling back to HTML.[/yellow]")

    # Generic HTML scraping
    log("  [dim]Fetching page...[/dim]")
    try:
        result = _scrape_generic(url)
    except Exception as e:
        log(f"  [yellow]HTTP fetch failed: {e}. Trying Playwright...[/yellow]")
        result = _scrape_with_playwright(url)

    # If content is too short, JS probably didn't render
    if len(result.get("description", "")) < 100:
        log("  [yellow]Content too short — retrying with Playwright...[/yellow]")
        try:
            result = _scrape_with_playwright(url)
        except Exception as e:
            log(f"  [red]Playwright also failed: {e}[/red]")

    return result


# ─── Company Research ─────────────────────────────────────────────


def research_company(
    company_name: str, console: Console | None = None
) -> str:
    """Research a company using Google (primary) with DuckDuckGo fallback.
    Returns concatenated search results as text.
    """
    log = console.print if console else print
    log(f"  [dim]Researching {company_name}...[/dim]")

    queries = [
        f"{company_name} recent news product launches 2025 2026",
        f"{company_name} product features latest",
    ]

    # Try Google first
    results = _search_google(queries)
    if results:
        log("  [dim]Found research via Google[/dim]")
        return results

    # Fallback to DuckDuckGo
    log("  [dim]Google unavailable, using DuckDuckGo...[/dim]")
    results = _search_duckduckgo(queries)
    if results:
        return results

    log("  [yellow]No research results found.[/yellow]")
    return ""


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
