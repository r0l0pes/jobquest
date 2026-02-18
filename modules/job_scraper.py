"""Job posting scraper and company research module.

Supports structured APIs for Greenhouse, Lever, Ashby, and Workable.
Falls back to generic HTML scraping, Firecrawl, then Playwright for JS-heavy pages.
Company research via Google (primary) with DuckDuckGo fallback.
"""

import os
import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from rich.console import Console

# Firecrawl API for enhanced web scraping (handles anti-bot, JS rendering)
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")


# ─── ATS URL Patterns ────────────────────────────────────────────

# Greenhouse: boards.greenhouse.io/{board}/jobs/{id} or job-boards.eu.greenhouse.io/{board}/jobs/{id}
_GREENHOUSE_PATTERN = re.compile(
    r"(?:boards|job-boards\.eu)\.greenhouse\.io/([\w-]+)/jobs/(\d+)"
)

# Lever: jobs.lever.co/{company}/{uuid}
_LEVER_PATTERN = re.compile(
    r"jobs\.lever\.co/([\w-]+)/([\w-]+)"
)

# Personio: {company}.jobs.personio.de/job/{id} or {company}.jobs.personio.com/job/{id}
_PERSONIO_PATTERN = re.compile(
    r"([\w-]+)\.jobs\.personio\.(?:de|com)/job/(\d+)"
)

# Screenloop: app.screenloop.com/careers/{company}/job_posts/{id}
_SCREENLOOP_PATTERN = re.compile(
    r"app\.screenloop\.com/careers/([\w-]+)/job_posts/(\d+)"
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

    # Company can be nested under "company" or directly as "company_name"
    # Also fallback to board name (usually matches company slug)
    company = data.get("company", {}).get("name", "")
    if not company:
        company = data.get("company_name", "")
    if not company:
        # Use board name as fallback, title-cased
        company = board.replace("-", " ").title()

    return {
        "title": data.get("title", ""),
        "company": company,
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


# ─── Personio & Screenloop ────────────────────────────────────────


def _scrape_personio(company: str, job_id: str) -> dict:
    """Personio job postings - uses HTML scraping with better selectors."""
    url = f"https://{company}.jobs.personio.de/job/{job_id}"
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Personio-specific selectors for title
    title = ""
    for selector in [
        "h1.job-title",
        "h1[data-testid='job-title']",
        ".job-details h1",
        "h1",
        "[class*='JobTitle']",
        "[class*='job-title']",
    ]:
        title_el = soup.select_one(selector)
        if title_el and title_el.get_text(strip=True):
            title = title_el.get_text(strip=True)
            break

    # Try extracting from og:title meta tag
    if not title:
        og_title = soup.select_one("meta[property='og:title']")
        if og_title:
            title = og_title.get("content", "")

    # Company name from subdomain or page
    company_name = company.replace("-", " ").title()
    company_el = soup.select_one(".company-name, [data-testid='company-name']")
    if company_el:
        company_name = company_el.get_text(strip=True)

    # Job description
    desc_el = soup.select_one(".job-description, [data-testid='job-description'], .job-details")
    if desc_el:
        description = desc_el.get_text(separator="\n", strip=True)
    else:
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        description = soup.get_text(separator="\n", strip=True)

    return {
        "title": title,
        "company": company_name,
        "description": description,
        "url": url,
        "source": "personio",
        "questions": [],
    }


def _scrape_screenloop(company: str, job_id: str) -> dict:
    """Screenloop job postings - JS-heavy, requires Playwright."""
    from playwright.sync_api import sync_playwright

    url = f"https://app.screenloop.com/careers/{company}/job_posts/{job_id}"
    company_name = company.replace("-", " ").title()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title = ""
    for selector in ["h1", ".job-title", "[data-testid='job-title']"]:
        title_el = soup.select_one(selector)
        if title_el and title_el.get_text(strip=True):
            title = title_el.get_text(strip=True)
            break

    # Try og:title
    if not title:
        og_title = soup.select_one("meta[property='og:title']")
        if og_title:
            title = og_title.get("content", "")

    # Company from og:site_name
    og_site = soup.select_one("meta[property='og:site_name']")
    if og_site:
        company_name = og_site.get("content", company_name)

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    description = soup.get_text(separator="\n", strip=True)

    return {
        "title": title,
        "company": company_name,
        "description": description,
        "url": url,
        "source": "screenloop",
        "questions": [],
    }


# ─── Generic Scraping ────────────────────────────────────────────


def _scrape_generic(url: str) -> dict:
    """Generic HTML scraping via requests + BeautifulSoup."""
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    return _extract_from_html(resp.text, url)


def _scrape_with_firecrawl(url: str) -> dict:
    """Scrape using Firecrawl API - handles JS, anti-bot, and complex pages."""
    if not FIRECRAWL_API_KEY:
        raise ValueError("FIRECRAWL_API_KEY not set")

    try:
        from firecrawl import FirecrawlApp
    except ImportError:
        raise ImportError("firecrawl-py not installed")

    app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
    doc = app.scrape(url, formats=["markdown", "html"], wait_for=3000)

    # Extract from markdown (cleaner) or fall back to HTML
    markdown = doc.markdown or ""
    html = doc.html or ""
    metadata = doc.metadata_dict or {}

    title = metadata.get("title", "")
    description = markdown if markdown else ""

    # If markdown is empty, try HTML
    if not description and html:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        description = soup.get_text(separator="\n", strip=True)

    # Extract company from og:site_name or URL
    company = metadata.get("ogSiteName", "")
    if not company:
        parsed = urlparse(url)
        company = parsed.hostname.split(".")[0].title() if parsed.hostname else ""

    return {
        "title": title,
        "company": company,
        "description": description,
        "url": url,
        "source": "firecrawl",
        "questions": [],
    }


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
    """Parse HTML and extract job posting data using multiple strategies."""
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    company = ""
    description = ""

    # Strategy 1: JSON-LD structured data (most reliable when present)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            # Handle array of objects
            if isinstance(data, list):
                for item in data:
                    if item.get("@type") == "JobPosting":
                        data = item
                        break
            if data.get("@type") == "JobPosting":
                title = title or data.get("title", "")
                company = company or data.get("hiringOrganization", {}).get("name", "")
                description = description or data.get("description", "")
                if "<" in description:
                    description = BeautifulSoup(description, "html.parser").get_text(
                        separator="\n", strip=True
                    )
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue

    # Strategy 2: Open Graph meta tags (widely used)
    if not title:
        og_title = soup.select_one("meta[property='og:title']")
        if og_title:
            title = og_title.get("content", "")

    if not company:
        og_site = soup.select_one("meta[property='og:site_name']")
        if og_site:
            company = og_site.get("content", "")

    # Strategy 3: Common CSS selectors for job boards
    if not title:
        for selector in [
            "h1.job-title",
            "h1.posting-headline",
            "[data-qa='job-title']",
            "[data-testid='job-title']",
            ".job-title h1",
            ".job-title",
            ".posting-title",
            "[class*='JobTitle']",
            "[class*='job-title']",
            "h1",
        ]:
            el = soup.select_one(selector)
            if el and el.get_text(strip=True):
                title = el.get_text(strip=True)
                break

    if not company:
        for selector in [
            ".company-name",
            "[data-qa='company-name']",
            "[data-testid='company-name']",
            "[class*='CompanyName']",
            "[class*='company-name']",
            ".employer-name",
            ".hiring-company",
        ]:
            el = soup.select_one(selector)
            if el and el.get_text(strip=True):
                company = el.get_text(strip=True)
                break

    # Strategy 4: Extract company from URL subdomain or path
    if not company:
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        path = parsed.path

        # Known ATS patterns where company is in subdomain
        ats_with_subdomain = ["personio", "recruitee", "bamboohr", "workday"]
        for ats in ats_with_subdomain:
            if ats in domain:
                # Company is likely the subdomain: company.jobs.personio.de
                parts = domain.split(".")
                if len(parts) > 2:
                    company = parts[0].replace("-", " ").title()
                break

        # Known ATS patterns where company is in path
        ats_with_path = ["greenhouse", "lever", "ashby", "workable", "screenloop"]
        if not company:
            for ats in ats_with_path:
                if ats in domain:
                    # Company is in path: /careers/{company}/ or /{company}/jobs/
                    path_parts = [p for p in path.split("/") if p]
                    if path_parts:
                        company = path_parts[0].replace("-", " ").title()
                    break

        # Last resort: use domain name if not a known ATS
        if not company:
            known_ats = [
                "greenhouse", "lever", "ashby", "workable", "personio",
                "smartrecruiters", "bamboohr", "recruitee", "screenloop",
                "workday", "icims", "taleo", "jobvite", "breezy",
            ]
            if not any(ats in domain for ats in known_ats):
                company = domain.split(".")[0].title()

    # Clean up HTML for description
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    if not description:
        # Try to find job description container
        for selector in [
            ".job-description",
            "[data-testid='job-description']",
            ".posting-description",
            ".job-details",
            "[class*='JobDescription']",
            "[class*='job-description']",
            "main",
            "article",
        ]:
            el = soup.select_one(selector)
            if el:
                description = el.get_text(separator="\n", strip=True)
                if len(description) > 200:
                    break

        # Fallback to full page text
        if len(description) < 200:
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

    personio = _PERSONIO_PATTERN.search(url)
    if personio:
        log("  [dim]Personio detected...[/dim]")
        try:
            return _scrape_personio(personio.group(1), personio.group(2))
        except Exception as e:
            log(f"  [yellow]Personio scrape failed: {e}. Falling back to generic.[/yellow]")

    screenloop = _SCREENLOOP_PATTERN.search(url)
    if screenloop:
        log("  [dim]Screenloop detected...[/dim]")
        try:
            return _scrape_screenloop(screenloop.group(1), screenloop.group(2))
        except Exception as e:
            log(f"  [yellow]Screenloop scrape failed: {e}. Falling back to generic.[/yellow]")

    # Generic HTML scraping
    log("  [dim]Fetching page...[/dim]")
    try:
        result = _scrape_generic(url)
    except Exception as e:
        log(f"  [yellow]HTTP fetch failed: {e}. Trying Playwright...[/yellow]")
        result = _scrape_with_playwright(url)

    # If content is too short or missing title/company, JS probably didn't render
    needs_enhanced = (
        len(result.get("description", "")) < 200
        or not result.get("title")
        or not result.get("company")
    )

    if needs_enhanced:
        # Try Firecrawl first (better anti-bot, JS handling)
        if FIRECRAWL_API_KEY:
            log("  [yellow]Incomplete data — trying Firecrawl...[/yellow]")
            try:
                fc_result = _scrape_with_firecrawl(url)
                if fc_result.get("description") and len(fc_result.get("description", "")) > len(result.get("description", "")):
                    result = fc_result
                    return result
            except Exception as e:
                log(f"  [dim]Firecrawl failed: {e}[/dim]")

        # Fall back to Playwright
        log("  [yellow]Retrying with Playwright...[/yellow]")
        try:
            pw_result = _scrape_with_playwright(url)
            # Merge: prefer Playwright results but keep any good data from HTML
            if pw_result.get("title") or not result.get("title"):
                result["title"] = pw_result.get("title") or result.get("title", "")
            if pw_result.get("company") or not result.get("company"):
                result["company"] = pw_result.get("company") or result.get("company", "")
            if len(pw_result.get("description", "")) > len(result.get("description", "")):
                result["description"] = pw_result["description"]
            result["source"] = "playwright"
        except Exception as e:
            log(f"  [yellow]Playwright failed: {e}. Using partial data.[/yellow]")

    return result


# ─── Company Research ─────────────────────────────────────────────


def _discover_important_pages(base_url: str) -> list[str]:
    """Discover important pages on a company website for research.

    Companies use different names for similar content. We look for all variations.
    """
    from urllib.parse import urljoin, urlparse

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


def research_company(
    company_name: str, company_url: str | None = None, console: Console | None = None
) -> str:
    """Research a company comprehensively for cover letter writing.

    Fetches multiple pages: homepage, about, solutions, case studies, etc.
    Returns company information as text for LLM context.
    """
    log = console.print if console else print
    log(f"  [dim]Researching {company_name}...[/dim]")

    results_text = []

    # Strategy 1: Deep crawl with Firecrawl (best for cover letters)
    if company_url and FIRECRAWL_API_KEY:
        log(f"  [dim]Deep research via Firecrawl: {company_url}[/dim]")
        try:
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

            # Discover important pages first
            pages_to_fetch = _discover_important_pages(company_url)
            log(f"  [dim]Found {len(pages_to_fetch)} pages to research[/dim]")

            for page_url in pages_to_fetch[:5]:  # Limit to 5 pages
                try:
                    doc = app.scrape(page_url, formats=["markdown"], wait_for=2000)
                    markdown = doc.markdown or ""
                    if markdown and len(markdown) > 100:
                        # Add section header based on URL
                        section = page_url.split("/")[-1] or "Homepage"
                        section = section.replace("-", " ").replace("_", " ").title()
                        results_text.append(f"## {section}\nSource: {page_url}\n\n{markdown[:2500]}")
                        log(f"  [dim]✓ Fetched: {section}[/dim]")
                except Exception as e:
                    continue

            if results_text:
                log(f"  [green]✓ Deep research complete ({len(results_text)} pages)[/green]")

        except Exception as e:
            log(f"  [yellow]Firecrawl deep research failed: {e}[/yellow]")

    # Strategy 2: Single page fetch (fallback)
    if not results_text and company_url:
        log(f"  [dim]Fetching company website: {company_url}[/dim]")
        try:
            direct_info = _fetch_company_page(company_url)
            if direct_info:
                results_text.append(f"Source: {company_url}\n\n{direct_info}")
                log("  [dim]✓ Company website fetched[/dim]")
        except Exception as e:
            log(f"  [yellow]Could not fetch company URL: {e}[/yellow]")

    # Strategy 2: Search (fallback)
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
