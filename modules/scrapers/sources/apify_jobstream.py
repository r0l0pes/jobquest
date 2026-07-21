"""Apify JobStream adapter — normalized job postings from Greenhouse, Lever, Ashby.

Uses the Apify JobStream Actor (brebiv/jobstream) to fetch normalized,
deduplicated, change-tracked job postings from the three major ATS platforms.
Requires APIFY_API_KEY env var.

Pricing: $2.50 / 1,000 job postings (pay per result, never for zero).
"""

import os
import re
import time
import json
import requests

from modules.scrapers.sources.base import JobDataSource
from modules.scrapers.sources.registry import JobSourceRegistry

# ATS URL patterns (shared with ats_api.py)
_GREENHOUSE_PATTERN = re.compile(
    r"(?:boards|job-boards\.eu)\.greenhouse\.io/([\w-]+)/jobs/(\d+)"
)
_LEVER_PATTERN = re.compile(
    r"jobs\.lever\.co/([\w-]+)/([\w-]+)"
)
_ASHBY_PATTERN = re.compile(
    r"jobs\.ashbyhq\.com/([\w-]+)(?:/([\w-]+))?"
)

# Apify JobStream Actor endpoint
APIFY_BASE_URL = "https://api.apify.com/v2"

# Wait parameters for run completion
_RUN_POLL_INTERVAL = 2  # seconds
_RUN_TIMEOUT = 30  # max seconds to wait for run


class ApifyJobStreamAdapter(JobDataSource):
    """Fetch normalized job postings via Apify JobStream Actor.

    Wraps the brebiv/jobstream Apify Actor for Greenhouse, Lever, and Ashby.
    Extracts company identifier from URL, calls the actor, and matches the
    returned job against the original URL.
    """

    def __init__(self):
        self._api_key = os.getenv("APIFY_API_KEY", "")

    def can_resolve(self, url: str) -> bool:
        """Return True if APIFY_API_KEY is set AND URL matches a supported ATS."""
        if not self._api_key:
            return False
        return self._extract_ats_type(url) is not None

    @property
    def priority(self) -> int:
        """Priority 20 — between direct ATS APIs (10) and stealth browsers (30).

        This adapter is used before agent-browser or generic HTML because Apify
        provides normalized, deduplicated data. Falls back to other adapters on
        API failures or missing key.
        """
        return 20

    def fetch(self, url: str) -> dict:
        """Fetch job posting via Apify JobStream.

        Args:
            url: Full job posting URL (Greenhouse, Lever, or Ashby).

        Returns:
            Job posting dict with keys: title, company, description, url, source, questions.

        Raises:
            RuntimeError: If Apify API call fails.
        """
        ats_type = self._extract_ats_type(url)
        if ats_type is None:
            raise RuntimeError(f"Unsupported ATS URL: {url}")

        company = self._extract_company_from_url(url)
        if company is None:
            raise RuntimeError(f"Cannot extract company from URL: {url}")

        # Call Apify JobStream Actor
        try:
            jobs = self._call_apify(ats_type, company)
        except Exception as e:
            raise RuntimeError(f"Apify JobStream failed for {url}: {e}")

        if not jobs:
            # No jobs returned — return minimal result, caller will fall back
            return {
                "title": "",
                "company": company.replace("-", " ").title(),
                "description": "",
                "url": url,
                "source": "apify",
                "questions": [],
            }

        # Try to match the specific job by URL
        matched = self._match_job_by_url(jobs, url)
        if matched is None:
            # No match — return first job as best guess with original URL
            return self._normalize_job_post(jobs[0], url)

        return self._normalize_job_post(matched, url)

    # ── URL parsing helpers ──

    def _extract_ats_type(self, url: str) -> str | None:
        """Identify which ATS platform the URL belongs to."""
        if _GREENHOUSE_PATTERN.search(url):
            return "greenhouse"
        if _LEVER_PATTERN.search(url):
            return "lever"
        if _ASHBY_PATTERN.search(url):
            return "ashby"
        return None

    def _extract_company_from_url(self, url: str) -> str | None:
        """Extract the company slug/identifier from the URL."""
        gh = _GREENHOUSE_PATTERN.search(url)
        if gh:
            return gh.group(1)

        lever = _LEVER_PATTERN.search(url)
        if lever:
            return lever.group(1)

        ashby = _ASHBY_PATTERN.search(url)
        if ashby:
            return ashby.group(1)

        return None

    def _extract_job_id(self, url: str) -> str | None:
        """Extract the job-specific identifier from the URL."""
        gh = _GREENHOUSE_PATTERN.search(url)
        if gh:
            return gh.group(2)

        lever = _LEVER_PATTERN.search(url)
        if lever:
            return lever.group(2)

        ashby = _ASHBY_PATTERN.search(url)
        if ashby:
            return ashby.group(2)

        return None

    def _match_job_by_url(self, jobs: list[dict], url: str) -> dict | None:
        """Find the job listing that matches the given URL.

        Tries exact job_id match first, then URL substring match.
        Returns the first job if nothing matches (best guess).
        """
        if not jobs:
            return None

        job_id = self._extract_job_id(url)

        # Exact match by job ID
        if job_id:
            for job in jobs:
                job_url = job.get("url", "")
                if job_id in job_url:
                    return job

        # Fallback: URL substring match (handle query params, tracking)
        url_lower = url.lower()
        for job in jobs:
            job_url = job.get("url", "").lower()
            if job_url and (job_url in url_lower or url_lower in job_url):
                return job

        # No match — return first as best guess
        return jobs[0]

    # ── Apify API calls ──

    def _call_apify(self, ats_type: str, company: str) -> list[dict]:
        """Call Apify JobStream Actor and return job listings.

        Args:
            ats_type: "greenhouse", "lever", or "ashby"
            company: Company slug/identifier

        Returns:
            List of job posting dicts from Apify.

        Raises:
            RuntimeError: If API call fails or times out.
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # Map our ATS names to Apify JobStream's format
        apify_source_map = {
            "greenhouse": "greenhouse",
            "lever": "lever",
            "ashby": "ashby",
        }
        source = apify_source_map.get(ats_type, ats_type)

        # Start the JobStream Actor run
        run_payload = {
            "actorId": "brebiv~jobstream",
            "input": {
                "source": source,
                "company": company,
                "maxJobs": 50,
            },
        }

        resp = requests.post(
            f"{APIFY_BASE_URL}/acts/brebiv~jobstream/runs",
            json=run_payload,
            headers=headers,
            timeout=30,
        )

        if resp.status_code == 401:
            raise RuntimeError("Apify API key is invalid or expired")
        if resp.status_code == 429:
            raise RuntimeError("Apify API rate limit exceeded")
        if resp.status_code != 201:
            raise RuntimeError(
                f"Apify API returned {resp.status_code}: {resp.text[:200]}"
            )

        run_data = resp.json().get("data", {})
        run_id = run_data.get("id")
        if not run_id:
            raise RuntimeError("Apify API did not return a run ID")

        # Poll for completion
        job_listings = self._poll_for_results(run_id, headers)
        return job_listings

    def _poll_for_results(self, run_id: str, headers: dict) -> list[dict]:
        """Poll Apify Actor run until completion, then fetch results.

        Args:
            run_id: Apify Actor run ID.
            headers: HTTP headers with auth token.

        Returns:
            List of job posting dicts from the dataset.

        Raises:
            RuntimeError: If run times out or fails.
        """
        start = time.time()
        while True:
            if time.time() - start > _RUN_TIMEOUT:
                raise RuntimeError(f"Apify JobStream run {run_id} timed out")

            status_resp = requests.get(
                f"{APIFY_BASE_URL}/actor-runs/{run_id}",
                headers=headers,
                timeout=15,
            )
            status_resp.raise_for_status()
            run_status = status_resp.json().get("data", {})
            status = run_status.get("status", "")

            if status == "SUCCEEDED":
                # Fetch the default dataset
                ds_resp = requests.get(
                    f"{APIFY_BASE_URL}/actor-runs/{run_id}/dataset/items",
                    headers=headers,
                    timeout=15,
                )
                if ds_resp.status_code == 200:
                    return ds_resp.json() or []
                return []

            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise RuntimeError(
                    f"Apify JobStream run {run_id} {status}: "
                    f"{run_status.get('statusMessage', '')}"
                )

            time.sleep(_RUN_POLL_INTERVAL)

    # ── Data normalization ──

    def _normalize_job_post(self, raw: dict, original_url: str | None = None) -> dict:
        """Normalize an Apify JobStream result to our JobPost format.

        Args:
            raw: Raw job dict from Apify JobStream.
            original_url: Optional override for the job URL.

        Returns:
            Normalized job posting dict.
        """
        # Strip HTML from description
        desc = raw.get("description") or raw.get("body") or ""
        if "<" in desc and ">" in desc:
            from bs4 import BeautifulSoup
            desc = BeautifulSoup(desc, "html.parser").get_text(
                separator="\n", strip=True
            )

        return {
            "title": raw.get("title", ""),
            "company": raw.get("company") or raw.get("organization") or "",
            "description": desc[:20000],
            "url": original_url or raw.get("url", ""),
            "source": "apify",
            "questions": raw.get("questions", []),
        }


# Self-register on import
JobSourceRegistry.register(ApifyJobStreamAdapter())
