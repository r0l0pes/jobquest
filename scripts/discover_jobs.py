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

import urllib.request
import urllib.error


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
    # Product Builder / Agentic AI
    ("Product Builder AI Germany", "ai", "de", "linkedin"),
    ("Senior Product Manager Builder AI Germany", "ai", "de", "linkedin"),
    ("AI-native Product Manager Germany", "ai", "de", "linkedin"),
    ("Agentic AI Product Manager Germany", "ai", "de", "linkedin"),
    ("Product Manager Agentic AI Germany", "ai", "de", "linkedin"),
    ("Product Builder AI Spain", "ai", "es", "linkedin"),
    ("AI Growth Automation Manager Germany", "growth", "de", "linkedin"),
    ("AI Growth Automation Manager Spain", "growth", "es", "linkedin"),
    ("AI Automation Manager Berlin", "growth", "de", "linkedin"),
    ("Product Manager AI Interfaces Germany", "ai", "de", "linkedin"),
    ("AI Interfaces Product Manager Berlin", "ai", "de", "linkedin"),
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
    # ── ES query rebalance (2026-06-28) ──
    # Growth PM — Spain
    ("Senior PM Growth B2B SaaS España", "growth", "es", "linkedin"),
    ("Product Manager Growth monetisation Spain remote", "growth", "es", "linkedin"),
    ("Senior PM activación retención España startup", "growth", "es", "infojobs"),
    # AI PM — Spain
    ("AI Product Manager Barcelona startup 2026", "ai", "es", "linkedin"),
    ("Senior PM AI ML España Madrid Valencia", "ai", "es", "linkedin"),
    ("Product Manager Generative AI Spain hiring", "ai", "es", "linkedin"),
    # Generalist PM — Spain
    ("Senior Product Manager SaaS España startup", "generalist", "es", "linkedin"),
    ("Senior Product Manager España fintech Barcelona", "generalist", "es", "linkedin"),
    ("Senior PM B2B Spain remote startup", "generalist", "es", "linkedin"),
    ("Product Manager ecommerce marketplace España", "generalist", "es", "infojobs"),
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
    return expected


def infer_location(title: str, url: str, country_hint: str) -> tuple[str | None, str | None]:
    """Try to extract location from title/URL. Returns (location, country).
    Returns (None, None) if the location is outside DE/ES/EU-remote.
    Uses a WHITELIST approach: only DE cities, ES cities, or explicit EU-remote signals.
    Anything else (US, India, LATAM, APAC, generic remote without EU signal) is rejected."""
    text = (title + " " + url).lower()
    # ── Whitelist: DE cities ──
    de_cities = ["berlin", "munich", "münchen", "hamburg", "cologne", "köln",
                 "frankfurt", "stuttgart", "düsseldorf", "leipzig", "dresden",
                 "nuremberg", "nürnberg", "heidelberg", "karlsruhe", "mannheim",
                 "bonn", "essen", "dortmund", "bremen"]
    for city in de_cities:
        if city in text:
            return (city.title(), "de")
    # ── Whitelist: ES cities ──
    es_cities = ["barcelona", "madrid", "valencia", "seville", "sevilla", "bilbao",
                 "málaga", "malaga", "zaragoza", "palma", "las palmas", "murcia",
                 "alicante", "granada", "valladolid", "san sebastián", "pamplona"]
    for city in es_cities:
        if city in text:
            return (city.title(), "es")
    # ── Explicit EU/EMEA remote signals (whitelist) ──
    eu_remote_signals = [
        "remote europe", "remote eu", "europe remote",
        "emea", "european time", "eu timezone",
        "cet", "gmt+1", "gmt+2", "utc+1", "utc+2",
        "emea remote", "remote dach", "remote de",
        "remote germany", "remote spain", "remote españa",
        "remote deutschland", "remote spanien",
        "remote in europe", "europe based",
    ]
    for sig in eu_remote_signals:
        if sig in text:
            return ("Remote", "remote")
    # ── Non-target location exclusion ──
    # Reject jobs from clearly non-DE/ES/EU locations before the country_hint
    # fallback can accept them. Only fires when no DE/ES city or EU-remote
    # signal matched above.
    non_target_signals = [
        "united states", "usa", "new york", "los angeles", "chicago",
        "san francisco", "boston", "seattle", "austin", "miami",
        "london", "uk", "united kingdom", "england", "manchester",
        "canada", "toronto", "vancouver", "montreal",
        "argentina", "buenos aires",
        "brazil", "brasil", "são paulo", "sao paulo", "rio de janeiro",
        "india", "mumbai", "bangalore", "delhi", "hyderabad",
        "singapore", "australia", "sydney", "melbourne",
        "japan", "tokyo", "mexico",
        "latam", "apac", "latin america",
        "middle east", "dubai", "uae",
    ]
    for sig in non_target_signals:
        if sig in text:
            return (None, None)
    # ── Remote fallback: if the query targeted remote roles and no non-target
    #    location was found above, accept as remote. The non-target exclusion list
    #    (just above) ensures non-EU jobs are still rejected.
    if country_hint == "remote":
        return ("Remote", "remote")
    # ── Country hint fallback (only DE/ES) ──
    if country_hint == "de":
        return ("Germany", "de")
    if country_hint == "es":
        return ("Spain", "es")
    # ── Everything else: reject ──
    return (None, None)


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
            "builder", "agentic", "automation", "interfaces",
        }
        parts = slug.split("-")
        company_parts = []
        for p in parts:
            if p.lower() in title_words:
                break
            if p.isdigit():
                continue
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


def exa_search(query: str, num_results: int = 10, mode: str = "7d") -> list[dict]:
    """Call Exa API via stdlib urllib. Returns list of result dicts.

    Args:
        query: The search query string.
        num_results: Max results to return per query.
        mode: Recency filter — "24h" (last 24 hours) or "7d" (last 7 days, default).
              When set, the API filters to results published after the cutoff date.
    """
    payload = {
        "query": query,
        "numResults": num_results,
        "type": "auto",
        "useAutoprompt": False,
    }
    # Apply recency filtering based on mode
    if mode == "24h":
        cutoff = (date.today() - timedelta(days=1)).isoformat()
        payload["startPublishedDate"] = cutoff
    elif mode == "7d":
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        payload["startPublishedDate"] = cutoff
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            EXA_SEARCH_URL,
            data=data,
            headers={
                "x-api-key": EXA_API_KEY or "",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read())
            return body.get("results", [])
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
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
    # ── Title-based filtering: must look like a Product Manager role ──
    title_lower = title.lower()
    # Must contain PM-related signal
    pm_signals = [
        "product manager", "product owner", "produktmanager", "product lead",
        "head of product", "vp product", "director of product",
        "product management", "produkt management", "product director",
        "growth product", "ai product", "product growth",
        "senior pm", "lead pm", "principal pm", "group product",
        "sr. product", "sr product", "product managerin",
        "produktmanagerin", "product management",
        "product builder", "ai interfaces", "ai growth",
        "agentic ai", "ai-native", "ai native",
    ]
    if not any(sig in title_lower for sig in pm_signals):
        return None
    # Exclude non-PM roles that still matched (e.g. "Backend Engineer" in a PM team page)
    exclude_title_signals = [
        "backend engineer", "frontend engineer", "software engineer",
        "devops", "data engineer", "qa engineer", "sre", "sales",
        "customer success manager", "customer success", "customer support",
        "account manager", "account executive", "business development",
        "marketing manager", "content manager", "social media",
        "recruiter", "talent acquisition", "hr manager",
        "sap", "consultant", "analyst", "data scientist",
        "prompt engineer", "community manager", "office manager",
        "full stack", "fullstack", "java developer", "python developer",
        "backend developer", "frontend developer", "ios developer",
        "android developer", "ux designer", "ui designer",
        "project manager", "program manager", "delivery manager",
        "scrum master", "agile coach", "implementation",
        "support engineer", "solutions engineer", "sales engineer",
        "partner manager", "alliance manager", "operation manager",
        "supply chain", "logistics", "finance manager",
        "legal counsel", "compliance", "security analyst",
    ]
    for bad in exclude_title_signals:
        if bad in title_lower:
            return None
    # Exclude news-like titles (long, descriptive, Spanish/German article headlines)
    news_indicators = [
        "claves", "lidera", "ofensiva", "aprueba", "convierte",
        "nueva era", "el poder de", "la verdad", "los que",
        "vamos a", "todos por", "subir márgenes", "captar inversión",
        "levanta", "seed:", "nombra a", "experto en",
        "oferta de", "oferta del", "consejo asesor",
        "para domar", "fomento de", "balance entre",
        "nadie le gusta", "1999", "2024", "2023", "2025",
    ]
    for ind in news_indicators:
        if ind in title_lower:
            return None
    # Exclude clickbait / generic listicles
    if re.search(r'^\d+\s', title) or "+" in title and "jobs" in title_lower:
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
        # Low-quality aggregators / freelancer platforms
        r"jaabz\.com", r"habooz\.com", r"jobleads\.com", r"mypivot\.work",
        r"sercanto\.com", r"simplyhired\.", r"freelancermap\.de",
        r"gulp\.de",
        # Scraper farms / spam job sites
        r"hirequorum\.liveblog365\.com", r"wfh\.hstn\.me",
        r"liveblog365\.com", r"likesyou\.org",
        r"wfhforgeon\.byethost7\.com", r"infinityfree\.me",
        r"quickswoop", r"careersync", r"zerogtalent", r"libertyloomtalent",
        r"jobradar24", r"adzuna", r"searchremotely",
        r"remotefront\.com", r"remotejobs\.iceiy",
        r"vibecodecareers", r"emploi\.strategies",
        # Spanish news / content aggregators posing as job boards
        r"noticiastrabajo", r"entornointeligente", r"telecombol",
        r"ecosistemastartup", r"murciastartup", r"mercado2",
        r"espanaesvoz", r"negocios", r"puestos.vacantes",
        # Generic news / content sites
        r"localnews\.com", r"erasmusforentrepreneurs",
        r"sarasatenea", r"montenegrobusiness", r"eventbrite",
        r"instagram\.com", r"facebook\.com", r"twitter\.com",
        # Events / talks / conferences
        r"/events/", r"/event/", r"/webinar", r"/conference",
        r"/talk/", r"/speaker/", r"/summit/",
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
    # Reject if location is outside DE/ES/EU-remote
    if location is None or country is None:
        return None
    # Reject if company name is garbage (generic words, too short, or clearly not a company)
    company = company or "Unknown"
    garbage_companies = {
        "unknown", "remote", "tech", "ai", "ml", "sr", "br", "rh", "on", "fo",
        "kn", "la", "te", "ne", "qu", "as", "pr", "ko", "ze", "ke",
        "prompt", "technical", "careersync", "experienced", "marketplace",
        "business development", "conversion rate optimization cro",
        "gtm partnerships", "alfatraining", "freelance it",
        "puestos vacantes consultor a sap sd mm retail",
        "produktmanager ki software m w d",
    }
    if company.lower() in garbage_companies:
        return None
    # Reject company names that are just 1-2 chars or look like fragments
    if len(company) <= 2 and company.lower() not in ("ibm", "hp", "ge", "bp"):
        return None
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


# ── URL verification (removed 2026-06-07) ──────────────────────────────────
# The verify_job_urls() function was removed because it:
# - Killed 86% of valid URLs (LinkedIn, StepStone, Join.com block HEAD requests)
# - Bottlenecked first-run discovery (350 URLs × 5s timeout blocked the subprocess)
# - Was defensive over-filtering — Exa's startPublishedDate already constrains recency
# The pipeline worked fine without it (Exa just returns some stale URLs occasionally).


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
        if company_counts.get(company, 0) >= 2:
            continue
        new_jobs.append(job)
        existing_urls.add(url)
        existing_keys.add(key)
        company_counts[company] = company_counts.get(company, 0) + 1
    return new_jobs


def group_jobs_for_output(jobs: list[dict]) -> str:
    """Format new jobs as JS array entries with section comments.

    Uses JS object notation (unquoted keys) instead of JSON so that
    parse_existing_jobs() can read back the entries on subsequent runs.
    """
    lines = []
    # Group by country then role
    countries = [("de", "🇩🇪 Germany"), ("es", "🇪🇸 Spain"), ("remote", "🌍 Remote")]
    roles = [("growth", "Growth PM"), ("ai", "AI PM"), ("generalist", "Generalist PM")]
    JS_KEYS = ["company", "title", "url", "companyUrl", "location",
               "country", "roleType", "date", "source"]
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
                parts = []
                for k in JS_KEYS:
                    v = j.get(k, "")
                    parts.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
                lines.append(f"    {{{', '.join(parts)}}},")
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
        results = exa_search(query, num_results=args.max_per_query, mode=args.mode)
        print(f"  → {len(results)} raw results", file=sys.stderr)
        for r in results:
            job = result_to_job(r, role_type, country_hint, expected_source)
            if job:
                all_new_jobs.append(job)

    print(f"\nTotal extracted: {len(all_new_jobs)}", file=sys.stderr)
    deduped = deduplicate_jobs(all_new_jobs, existing)
    print(f"New after dedup: {len(deduped)}", file=sys.stderr)

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
