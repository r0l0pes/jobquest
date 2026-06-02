#!/usr/bin/env python3
"""Discover PM jobs via direct Exa API calls. Bypasses pi's broken web_search tool.

Usage:
    source venv/bin/activate
    python scripts/discover_jobs.py --mode 7d
    python scripts/discover_jobs.py --mode 24h

The script reads ~/.pi/web-search.json for the Exa API key, runs semantic
searches, extracts job postings, deduplicates against data/job_queue.html,
and appends new entries.
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests


EXA_SEARCH_URL = "https://api.exa.ai/search"
EXA_API_KEY = None
QUEUE_PATH = Path("data/job_queue.html")

# ── Query catalog ───────────────────────────────────────────────────────────
# Each entry: (query, role_type, country_hint, expected_source)
# Exa is semantic — no site: operators needed. Plain language works best.

QUERY_CATALOG = [
    # Growth PM — Germany
    ("Senior Growth Product Manager jobs Germany 2026", "growth", "de", "linkedin"),
    ("Product Manager Growth Deutschland hiring", "growth", "de", "stepstone"),
    ("Senior PM Growth Monetisation Germany", "growth", "de", "linkedin"),
    ("Growth Product Lead Berlin Munich Hamburg", "growth", "de", "linkedin"),
    ("Senior Produktmanager Wachstum Deutschland", "growth", "de", "stepstone"),
    # Growth PM — Spain
    ("Senior Growth Product Manager jobs Spain 2026", "growth", "es", "linkedin"),
    ("Product Manager Growth España contratación", "growth", "es", "infojobs"),
    ("Senior PM Growth Barcelona Madrid Valencia", "growth", "es", "linkedin"),
    # AI PM — Germany
    ("Senior AI Product Manager jobs Germany 2026", "ai", "de", "linkedin"),
    ("AI Product Manager Deutschland hiring machine learning", "ai", "de", "stepstone"),
    ("Senior PM AI Platform Berlin Munich", "ai", "de", "linkedin"),
    ("Product Manager Generative AI Germany", "ai", "de", "linkedin"),
    # AI PM — Spain
    ("Senior AI Product Manager jobs Spain 2026", "ai", "es", "linkedin"),
    ("Product Manager AI España Barcelona Madrid", "ai", "es", "linkedin"),
    # Generalist PM — Germany
    ("Senior Product Manager jobs Germany 2026", "generalist", "de", "linkedin"),
    ("Senior Produktmanager Deutschland Berlin", "generalist", "de", "stepstone"),
    ("Senior PM SaaS B2B Germany hiring", "generalist", "de", "linkedin"),
    ("Senior Product Manager startup Deutschland", "generalist", "de", "linkedin"),
    # Generalist PM — Spain
    ("Senior Product Manager jobs Spain 2026", "generalist", "es", "linkedin"),
    ("Senior Product Manager España Barcelona Madrid", "generalist", "es", "linkedin"),
    ("Product Manager SaaS Spain hiring", "generalist", "es", "linkedin"),
    # Remote / EU-wide
    ("Senior Product Manager remote Europe EU timezone", "generalist", "remote", "remoteok"),
    ("Senior Growth Product Manager remote Europe hiring", "growth", "remote", "weworkremotely"),
    ("AI Product Manager remote Europe 2026", "ai", "remote", "remoteok"),
    ("Product Manager remote EU startup", "generalist", "remote", "wellfound"),
    # Startup-focused
    ("Senior Product Manager Berlin startup hiring", "generalist", "de", "linkedin"),
    ("Senior PM Barcelona startup fintech", "generalist", "es", "linkedin"),
    ("Growth PM startup Germany hiring 2026", "growth", "de", "linkedin"),
    # German language
    ("Senior Produktmanager Experimentierung Conversion Deutschland", "growth", "de", "stepstone"),
    ("Produktmanager Activation Retention Deutschland", "growth", "de", "stepstone"),
    # Spanish language
    ("Senior Product Manager experimentación conversión España", "growth", "es", "infojobs"),
    ("Product Manager activación retención España", "growth", "es", "infojobs"),
    # E-commerce / Marketplace
    ("Senior Product Manager ecommerce marketplace Germany", "generalist", "de", "linkedin"),
    ("Senior PM payments checkout Germany", "growth", "de", "linkedin"),
    # Experimentation & Conversion
    ("Senior Product Manager conversion A/B testing Germany", "growth", "de", "linkedin"),
    ("Senior PM experimentation funnel optimisation", "growth", "de", "linkedin"),
    # PLG / Monetisation
    ("Senior Product Manager product-led growth Germany", "growth", "de", "linkedin"),
    ("Senior PM pricing packaging monetisation", "growth", "de", "linkedin"),
    # ── New remote job boards ──
    ("Senior Product Manager 4dayweek remote Europe", "generalist", "remote", "4dayweek"),
    ("Senior Growth PM 4dayweek remote Europe", "growth", "remote", "4dayweek"),
    ("Product Manager remote jobspresso Europe", "generalist", "remote", "jobspresso"),
    ("Growth Product Manager remote jobspresso Europe", "growth", "remote", "jobspresso"),
    ("Senior Product Manager flexjobs remote", "generalist", "remote", "flexjobs"),
    ("Senior PM nodesk remote Europe", "generalist", "remote", "nodesk"),
    ("AI Product Manager nodesk remote", "ai", "remote", "nodesk"),
    ("Product Manager working nomads remote Europe", "generalist", "remote", "workingnomads"),
    ("Senior Growth PM working nomads remote", "growth", "remote", "workingnomads"),
    ("Senior Product Manager truly remote Europe", "generalist", "remote", "trulyremote"),
    ("Product Manager flexa careers remote", "generalist", "remote", "flexa"),
    ("Senior PM jobgether remote Europe", "generalist", "remote", "jobgether"),
    ("Growth PM jobgether remote", "growth", "remote", "jobgether"),
    ("Product Manager oomple freelance remote", "generalist", "remote", "oomple"),
    ("Senior Product Manager careervault remote", "generalist", "remote", "careervault"),
    ("AI Product Manager careervault remote", "ai", "remote", "careervault"),
    ("Senior Product Manager dailyremote Europe", "generalist", "remote", "dailyremote"),
    ("Senior Growth PM dailyremote", "growth", "remote", "dailyremote"),
    ("Senior PM remotely de Germany", "generalist", "de", "remotely.de"),
    ("Product Manager eu remote jobs Europe", "generalist", "remote", "euremotejobs"),
    # Google Jobs — converts at 2.4x LinkedIn rate per Huntr Q1 2026
    ("Senior Product Manager Germany site:google.com/search", "generalist", "de", "google"),
    ("Growth Product Manager Germany site:google.com/search", "growth", "de", "google"),
    ("AI Product Manager Germany site:google.com/search", "ai", "de", "google"),
    ("Senior Product Manager Spain site:google.com/search", "generalist", "es", "google"),
]


def load_exa_key():
    """Read Exa API key from pi's web-search config."""
    global EXA_API_KEY
    config_path = Path.home() / ".pi" / "web-search.json"
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f)
        EXA_API_KEY = cfg.get("exaApiKey") or cfg.get("EXA_API_KEY")
    if not EXA_API_KEY:
        EXA_API_KEY = os.environ.get("EXA_API_KEY")
    if not EXA_API_KEY:
        raise RuntimeError(
            "No Exa API key found. Set it in ~/.pi/web-search.json under 'exaApiKey' "
            "or set EXA_API_KEY environment variable."
        )
    return EXA_API_KEY


def parse_existing_jobs(html_path: Path) -> list[dict]:
    """Extract the JOBS array from the HTML file.

    The HTML uses JS object notation (unquoted keys), not valid JSON.
    We extract fields via regex rather than json.loads.
    """
    if not html_path.exists():
        return []
    text = html_path.read_text(encoding="utf-8")
    match = re.search(r"const\s+JOBS\s*=\s*(\[.*?\]);", text, re.DOTALL)
    if not match:
        return []
    array_text = match.group(1)
    jobs = []
    object_blocks = re.findall(r"\{[^{}]*\}", array_text, re.DOTALL)
    for block in object_blocks:
        job = {}
        for key in ("company", "title", "url", "companyUrl", "location",
                    "country", "roleType", "date", "source"):
            m = re.search(rf"\b{key}\s*:\s*\"([^\"]*)\"", block)
            if m:
                job[key] = m.group(1)
            else:
                m = re.search(rf"\b{key}\s*:\s*'([^']*)'", block)
                if m:
                    job[key] = m.group(1)
        if job.get("url"):
            jobs.append(job)
    return jobs


def extract_domain(url: str) -> str:
    """Extract the domain name from a URL."""
    m = re.match(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else ""


def infer_source(url: str, expected: str) -> str:
    """Infer the job board source from the URL."""
    domain = extract_domain(url).lower()
    if "linkedin" in domain:
        return "linkedin"
    if "stepstone" in domain:
        return "stepstone"
    if "infojobs" in domain:
        return "infojobs"
    if "indeed" in domain:
        return "indeed"
    if "wellfound" in domain or "angel.co" in domain:
        return "wellfound"
    if "weworkremotely" in domain:
        return "weworkremotely"
    if "remoteok" in domain:
        return "remoteok"
    if "himalayas" in domain:
        return "himalayas"
    if "remotive" in domain:
        return "remotive"
    if "arbeitsagentur" in domain or "arbeitnow" in domain:
        return "arbeitnow"
    if "workwise" in domain:
        return "workwise"
    if "jobs.lever.co" in domain:
        return "lever"
    if "greenhouse" in domain:
        return "greenhouse"
    if "apply.workable" in domain or "workable" in domain:
        return "workable"
    if "careers" in domain or "jobs" in domain:
        return "company"
    if "4dayweek" in domain:
        return "4dayweek"
    if "jobspresso" in domain:
        return "jobspresso"
    if "flexjobs" in domain:
        return "flexjobs"
    if "nodesk" in domain:
        return "nodesk"
    if "workingnomads" in domain:
        return "workingnomads"
    if "trulyremote" in domain:
        return "trulyremote"
    if "flexa" in domain:
        return "flexa"
    if "jobgether" in domain:
        return "jobgether"
    if "oomple" in domain:
        return "oomple"
    if "careervault" in domain:
        return "careervault"
    if "dailyremote" in domain:
        return "dailyremote"
    if "google.com/search" in domain or "google" in domain and "jobs" in url.lower():
        return "google"
    return expected


def infer_location(title: str, url: str, country_hint: str) -> tuple[str, str]:
    """Try to extract location from title/URL. Returns (location, country)."""
    text = (title + " " + url).lower()
    # Check for remote markers
    if any(r in text for r in ["remote", "fully remote", "100% remote", "home office"]):
        return ("Remote", "remote")
    # Country-specific cities
    de_cities = ["berlin", "munich", "münchen", "hamburg", "cologne", "köln",
                 "frankfurt", "stuttgart", "düsseldorf", "leipzig", "dresden",
                 "nuremberg", "nürnberg", "heidelberg", "karlsruhe", "mannheim",
                 "bonn", "essen", "dortmund", "bremen"]
    es_cities = ["barcelona", "madrid", "valencia", "seville", "sevilla", "bilbao",
                 "málaga", "malaga", "zaragoza", "palma", "las palmas", "murcia",
                 "alicante", "granada", "valladolid", "san sebastián", "pamplona"]
    for city in de_cities:
        if city in text:
            return (city.title(), "de")
    for city in es_cities:
        if city in text:
            return (city.title(), "es")
    # Default to country hint
    loc = "Germany" if country_hint == "de" else "Spain" if country_hint == "es" else "Remote"
    return (loc, country_hint)


def clean_company_name(raw: str) -> str:
    """Clean up company name from Exa result."""
    # Remove common suffixes
    raw = re.sub(r"\s*(jobs|careers|hiring|gmbh|ag|ug|sl|s\.l|inc|llc|ltd)\.*$", "", raw, flags=re.I)
    # Remove location suffixes like "- Berlin" or "| Munich"
    raw = re.sub(r"[-|]\s*\w+\s*$", "", raw)
    return raw.strip()


def clean_title(raw: str) -> str:
    """Clean up job title from Exa result."""
    # Remove location suffix like "• München, Bavaria, Germany"
    raw = re.sub(r"\s*[•\-]\s*.*$", "", raw)
    # Remove company suffix if present
    raw = re.sub(r"\s*at\s+[^,]+$", "", raw, flags=re.I)
    raw = re.sub(r"\s*[-|]\s*[^,]+$", "", raw)
    return raw.strip()


KNOWN_JOB_BOARDS = {
    "linkedin", "stepstone", "indeed", "infojobs", "wellfound", "angel",
    "weworkremotely", "remoteok", "himalayas", "remotive", "arbeitnow",
    "workwise", "bebee", "join.com", "remotely.de", "remoteitjobs",
    "euremotejobs", "marketingmonk", "talents.studysmarter",
    "startup-insider", "personio",
    "4dayweek", "jobspresso", "flexjobs", "nodesk",
    "workingnomads", "trulyremote", "flexa", "jobgether",
    "oomple", "careervault", "dailyremote",
}


def extract_company_from_url(url: str) -> str:
    """Try to extract real company name from job-board URL paths."""
    url_lower = url.lower()
    # 1. Subdomain patterns: company.jobs.personio.com, company.greenhouse.io, etc.
    subdomain_patterns = [
        r"https?://([\w-]+)\.jobs\.personio",
        r"https?://([\w-]+)\.greenhouse\.io",
        r"https?://([\w-]+)\.lever\.co",
        r"https?://([\w-]+)\.workable\.com",
        r"https?://boards\.greenhouse\.io/([\w-]+)",
    ]
    for pat in subdomain_patterns:
        m = re.search(pat, url_lower)
        if m:
            name = m.group(1).replace("-", " ").replace("_", " ").title()
            return clean_company_name(name)
    # 2. Path patterns
    path_patterns = [
        # join.com/companies/company-name/...
        r"/companies/([^/]+)/",
        # talents.studysmarter.de/companies/company-name/...
        r"talents\.studysmarter\.de/companies/([^/]+)/",
        # marketingmonk.so/jobboard/jobs/...-at-company-name-...
        r"/jobs/[^/]*-at-([^/-]+)",
        # general /careers/company
        r"/careers/([^/]+)",
    ]
    for pat in path_patterns:
        m = re.search(pat, url_lower)
        if m:
            name = m.group(1).replace("-", " ").replace("_", " ").title()
            return clean_company_name(name)
    # 3. /job/ slug extraction: try first segment after /job/
    # e.g. remoteitjobs.app/job/laserhub-gmbh-product-manager...
    m = re.search(r"/job/([\w-]+)", url_lower)
    if m:
        slug = m.group(1)
        # Split by dash and take words until we hit a common title word
        title_words = {
            "senior", "junior", "lead", "principal", "head", "director",
            "vp", "manager", "product", "growth", "ai", "engineer", "designer",
            "sales", "marketing", "analyst", "specialist", "coordinator",
            "remote", "hybrid", "berlin", "munich", "hamburg", "madrid",
            "barcelona", "full", "time", "part", "intern", "entry",
            "dach", "europe", "emea", "apac", "global", "worldwide",
        }
        parts = slug.split("-")
        company_parts = []
        for p in parts:
            if p.lower() in title_words:
                break
            company_parts.append(p)
        if company_parts:
            name = " ".join(company_parts).title()
            return clean_company_name(name)
    return ""


def extract_company_from_title(title: str) -> str:
    """Try to extract company name from title using common patterns."""
    # English: "at Company" or "| Company"
    m = re.search(r"at\s+([A-Z][A-Za-z0-9\s&]+?)(?:\s*[,-•]|\s*$)", title)
    if m:
        return clean_company_name(m.group(1))
    # German: "bei Company"
    m = re.search(r"bei\s+([A-Z][A-Za-z0-9\s&]+?)(?:\s*[,-]|\s*$)", title)
    if m:
        return clean_company_name(m.group(1))
    return ""


def extract_company_from_domain(url: str) -> str:
    """Extract company name from domain, but skip known job boards."""
    domain = extract_domain(url).lower()
    parts = domain.replace("www.", "").split(".")
    base = parts[0] if parts else ""
    for board in KNOWN_JOB_BOARDS:
        if board in base or board in domain:
            return ""
    return clean_company_name(base.replace("-", " ").title())


def exa_search(query: str, num_results: int = 10) -> list[dict]:
    """Call Exa API directly. Returns list of result dicts."""
    headers = {
        "x-api-key": EXA_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "numResults": num_results,
        "type": "auto",
        "useAutoprompt": False,
        # Exa supports recency filtering via includeDomains or text filtering
        # but plain semantic search is most reliable
    }
    try:
        resp = requests.post(EXA_SEARCH_URL, headers=headers, json=payload, timeout=45)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except requests.RequestException as e:
        print(f"  [Exa error] {query[:50]}... → {e}", file=sys.stderr)
        return []


def result_to_job(result: dict, role_type: str, country_hint: str, expected_source: str) -> dict | None:
    """Convert an Exa result into a structured job dict. Returns None if invalid."""
    url = result.get("url", "").strip()
    title = result.get("title", "").strip()
    if not url or not title:
        return None
    # Skip very short titles (likely person names or generic pages, not jobs)
    if len(title) < 12:
        return None
    # Skip non-job results (blogs, news, generic pages, personal profiles)
    skip_patterns = [
        r"/blog", r"/news", r"/article", r"/press", r"/about",
        r"/company", r"/culture", r"/team", r"/insights", r"/resources",
        r"\.pdf$", r"medium\.com", r"substack\.com", r"news\.yahoo",
        r" indeed\.com/career", r"glassdoor",
        # Personal profiles / portfolios
        r"/profile", r"/people", r"/portfolio", r"\.cv/", r"/resume",
        r"linkedin\.com/in/", r"xing\.com/profile",
        r"/whoiswho", r"/whoswho", r"/org-chart",
        r"/p/\w+-resume", r"/p/\w+-cv",
        # Personal portfolio path indicators (covers Spanish + English)
        r"/sobre-mi", r"/conoce-a", r"/curriculum", r"/cv/",
        # Known personal-site / portfolio domains
        # When you find a personal portfolio leaking through, add its domain here.
        r"sarahdrivesgrowth\.com", r"prod-pulse\.com", r"hello\.cv",
        r"philippgerard\.de", r"luizdavi\.com", r"majidm\.com",
        r"danielle\.mt", r"tuccio\.de", r"experimentationcareer\.com",
        r"success\.ai/profile", r"twine\.net",
        r"gonzalolluch\.com", r"hectorodriguezsoto\.com", r"francastillo\.me",
        r"josepjorba\.com", r"pablomoratinos\.es", r"franlopezballero\.com",
        r"arrabal\.vinegla\.com", r"carloslopezcebollero\.com", r"mrmoises\.es",
        r"evaplutopamal\.com", r"sara-fernandez\.com", r"thenomadicpm\.com",
        r"anamariazamfirache\.com", r"danielleduijst\.com", r"ilias\.pm",
        r"franzheinfling\.com",
        # Low-quality aggregators / freelancer platforms
        r"jaabz\.com", r"habooz\.com", r"jobleads\.com", r"mypivot\.work",
        r"sercanto\.com", r"simplyhired\.", r"freelancermap\.de",
        r"gulp\.de",
    ]
    url_lower = url.lower()
    for pat in skip_patterns:
        if re.search(pat, url_lower):
            return None
    # Try to extract company: URL path first (best for job boards),
    # then title, then domain
    company = extract_company_from_url(url)
    if not company:
        company = extract_company_from_title(title)
    if not company:
        company = extract_company_from_domain(url)
    clean = clean_title(title)
    location, country = infer_location(title, url, country_hint)
    source = infer_source(url, expected_source)
    return {
        "company": company or "Unknown",
        "title": clean or title,
        "url": url,
        "companyUrl": "",
        "location": location,
        "country": country,
        "roleType": role_type,
        "date": date.today().isoformat(),
        "source": source,
    }


# ── URL verification (added 2026-05-24) ──────────────────────────────────────
# Revert note: if this causes jobs to be lost or slows discovery too much,
# delete the verify_job_urls() function and remove the call in main().
# The pipeline worked fine without it — Exa just returns some stale URLs.

def verify_job_urls(jobs: list[dict], timeout: int = 5) -> list[dict]:
    """HEAD-check each job URL and return only jobs that are still alive.

    Keeps URLs that return 200, 301, or 302. Skips 404, 410, 5xx,
    and connection failures (including SSLError/timeout).
    """
    live = []
    dead = 0
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko)"
    )
    for job in jobs:
        url = job["url"]
        try:
            resp = session.head(url, timeout=timeout, allow_redirects=True)
            if resp.status_code < 400:
                live.append(job)
            else:
                dead += 1
                print(f"  [dead {resp.status_code}] {url[:80]}", file=sys.stderr)
        except requests.RequestException:
            dead += 1
            print(f"  [dead conn-err] {url[:80]}", file=sys.stderr)
    if dead:
        print(f"  → Skipped {dead} dead/stale URLs", file=sys.stderr)
    print(f"  → {len(live)} jobs verified alive", file=sys.stderr)
    return live


def deduplicate_jobs(jobs: list[dict], existing: list[dict]) -> list[dict]:
    """Remove duplicates against existing jobs."""
    existing_urls = {j["url"] for j in existing}
    existing_keys = {(j.get("company", "").lower(), j.get("title", "").lower()) for j in existing}
    company_counts = {}
    for j in existing:
        c = j.get("company", "").lower()
        company_counts[c] = company_counts.get(c, 0) + 1
    new_jobs = []
    for job in jobs:
        url = job["url"]
        key = (job["company"].lower(), job["title"].lower())
        company = job["company"].lower()
        if url in existing_urls:
            continue
        if key in existing_keys:
            continue
        if company_counts.get(company, 0) >= 1:
            continue
        new_jobs.append(job)
        existing_urls.add(url)
        existing_keys.add(key)
        company_counts[company] = company_counts.get(company, 0) + 1
    return new_jobs


def group_jobs_for_output(jobs: list[dict]) -> str:
    """Format new jobs as JS array entries with section comments."""
    lines = []
    # Group by country then role
    countries = [("de", "🇩🇪 Germany"), ("es", "🇪🇸 Spain"), ("remote", "🌍 Remote")]
    roles = [("growth", "Growth PM"), ("ai", "AI PM"), ("generalist", "Generalist PM")]
    for ccode, clabel in countries:
        country_jobs = [j for j in jobs if j["country"] == ccode]
        if not country_jobs:
            continue
        lines.append(f"    // {clabel}")
        for rcode, rlabel in roles:
            role_jobs = [j for j in country_jobs if j["roleType"] == rcode]
            if not role_jobs:
                continue
            lines.append(f"    // {clabel} — {rlabel}")
            for j in role_jobs:
                entry = json.dumps(j, ensure_ascii=False)
                lines.append(f"    {entry},")
        lines.append("")
    return "\n".join(lines)


def append_to_queue(html_path: Path, new_jobs: list[dict]):
    """Append new jobs to the JOBS array in the HTML file."""
    if not new_jobs:
        return
    text = html_path.read_text(encoding="utf-8")
    # Find the end of the JOBS array: the closing `];`
    match = re.search(r"(const\s+JOBS\s*=\s*\[.*?)(\];)", text, re.DOTALL)
    if not match:
        print("[warn] Could not find JOBS array in HTML.", file=sys.stderr)
        return
    prefix = text[:match.end(1)]
    suffix = text[match.start(2):]
    # Generate the new entries
    grouped = group_jobs_for_output(new_jobs)
    # Insert before the closing ]; — add a newline before if prefix doesn't end with one
    if not prefix.rstrip().endswith(",") and not prefix.rstrip().endswith("["):
        # Add trailing comma to last existing entry if needed
        prefix = prefix.rstrip() + ",\n"
    else:
        prefix = prefix.rstrip() + "\n"
    new_text = prefix + grouped.rstrip() + "\n" + suffix
    html_path.write_text(new_text, encoding="utf-8")
    print(f"Appended {len(new_jobs)} jobs to {html_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Discover PM jobs via Exa API")
    parser.add_argument("--mode", choices=["24h", "7d"], default="7d",
                        help="Recency filter: 24h = last 24 hours, 7d = last 7 days")
    parser.add_argument("--max-per-query", type=int, default=8,
                        help="Max results per query (default: 8)")
    parser.add_argument("--queries", type=int, default=None,
                        help="Limit number of queries to run (for testing)")
    args = parser.parse_args()

    load_exa_key()
    print(f"Mode: {args.mode} | Exa key loaded OK", file=sys.stderr)

    existing = parse_existing_jobs(QUEUE_PATH)
    print(f"Existing jobs in queue: {len(existing)}", file=sys.stderr)

    all_new_jobs = []
    queries = QUERY_CATALOG[:args.queries] if args.queries else QUERY_CATALOG

    for idx, (query, role_type, country_hint, expected_source) in enumerate(queries, 1):
        print(f"\n[{idx}/{len(queries)}] Searching: {query}", file=sys.stderr)
        results = exa_search(query, num_results=args.max_per_query)
        print(f"  → {len(results)} raw results", file=sys.stderr)
        for r in results:
            job = result_to_job(r, role_type, country_hint, expected_source)
            if job:
                all_new_jobs.append(job)

    print(f"\nTotal extracted: {len(all_new_jobs)}", file=sys.stderr)
    deduped = deduplicate_jobs(all_new_jobs, existing)
    print(f"New after dedup: {len(deduped)}", file=sys.stderr)

    if deduped:
        print(f"\nVerifying {len(deduped)} job URLs are still active...", file=sys.stderr)
        deduped = verify_job_urls(deduped)
    if deduped:
        append_to_queue(QUEUE_PATH, deduped)
        print(f"\n✅ Added {len(deduped)} new jobs to {QUEUE_PATH}", file=sys.stderr)
    else:
        print(f"\nℹ️ No new jobs found.", file=sys.stderr)

    # Print JSON summary to stdout for downstream parsing
    print(json.dumps({
        "mode": args.mode,
        "queries_run": len(queries),
        "existing": len(existing),
        "extracted": len(all_new_jobs),
        "added": len(deduped),
        "new_jobs": deduped,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
