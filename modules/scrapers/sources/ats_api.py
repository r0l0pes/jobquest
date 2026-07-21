"""ATS API adapters for job posting scraping.

Each adapter wraps the existing _scrape_* functions in job_postings.py.
Self-registers with the JobSourceRegistry at module load time.
"""

import re

from modules.scrapers.sources.base import JobDataSource
from modules.scrapers.sources.registry import JobSourceRegistry

# ─── URL Patterns (mirrored from job_postings.py for adapter use) ───

_GREENHOUSE_PATTERN = re.compile(
    r"(?:boards|job-boards\.eu)\.greenhouse\.io/([\w-]+)/jobs/(\d+)"
)

_LEVER_PATTERN = re.compile(
    r"jobs\.lever\.co/([\w-]+)/([\w-]+)"
)

_PERSONIO_PATTERN = re.compile(
    r"([\w-]+)\.jobs\.personio\.(?:de|com)/job/(\d+)"
)

_SCREENLOOP_PATTERN = re.compile(
    r"app\.screenloop\.com/careers/([\w-]+)/job_posts/(\d+)"
)

_ASHBY_PATTERN = re.compile(
    r"jobs\.ashbyhq\.com/([\w-]+)(?:/([\w-]+))?"
)

_WORKABLE_PATTERN = re.compile(
    r"apply\.workable\.com/([\w-]+)/j/([\w-]+)"
)


class GreenhouseAdapter(JobDataSource):
    """Greenhouse public boards API."""

    def can_resolve(self, url: str) -> bool:
        return bool(_GREENHOUSE_PATTERN.search(url))

    def fetch(self, url: str) -> dict:
        from modules.scrapers.job_postings import _scrape_greenhouse

        gh = _GREENHOUSE_PATTERN.search(url)
        if gh is None:
            raise ValueError(f"Not a Greenhouse URL: {url}")
        return _scrape_greenhouse(gh.group(1), gh.group(2))

    @property
    def priority(self) -> int:
        return 10


class LeverAdapter(JobDataSource):
    """Lever public postings API."""

    def can_resolve(self, url: str) -> bool:
        return bool(_LEVER_PATTERN.search(url))

    def fetch(self, url: str) -> dict:
        from modules.scrapers.job_postings import _scrape_lever

        lev = _LEVER_PATTERN.search(url)
        if lev is None:
            raise ValueError(f"Not a Lever URL: {url}")
        return _scrape_lever(lev.group(1), lev.group(2))

    @property
    def priority(self) -> int:
        return 10


class AshbyAdapter(JobDataSource):
    """Ashby public job posting API (GraphQL)."""

    def can_resolve(self, url: str) -> bool:
        return bool(_ASHBY_PATTERN.search(url))

    def fetch(self, url: str) -> dict:
        from modules.scrapers.job_postings import _scrape_ashby

        ash = _ASHBY_PATTERN.search(url)
        if ash is None:
            raise ValueError(f"Not an Ashby URL: {url}")
        return _scrape_ashby(ash.group(1), ash.group(2))

    @property
    def priority(self) -> int:
        return 10


class WorkableAdapter(JobDataSource):
    """Workable public widget API."""

    def can_resolve(self, url: str) -> bool:
        return bool(_WORKABLE_PATTERN.search(url))

    def fetch(self, url: str) -> dict:
        from modules.scrapers.job_postings import _scrape_workable

        wk = _WORKABLE_PATTERN.search(url)
        if wk is None:
            raise ValueError(f"Not a Workable URL: {url}")
        return _scrape_workable(wk.group(1), wk.group(2))

    @property
    def priority(self) -> int:
        return 10


class PersonioAdapter(JobDataSource):
    """Personio job postings (HTML scraping)."""

    def can_resolve(self, url: str) -> bool:
        return bool(_PERSONIO_PATTERN.search(url))

    def fetch(self, url: str) -> dict:
        from modules.scrapers.job_postings import _scrape_personio

        pio = _PERSONIO_PATTERN.search(url)
        if pio is None:
            raise ValueError(f"Not a Personio URL: {url}")
        return _scrape_personio(pio.group(1), pio.group(2))

    @property
    def priority(self) -> int:
        return 10


class ScreenloopAdapter(JobDataSource):
    """Screenloop job postings (JS-heavy, Playwright)."""

    def can_resolve(self, url: str) -> bool:
        return bool(_SCREENLOOP_PATTERN.search(url))

    def fetch(self, url: str) -> dict:
        from modules.scrapers.job_postings import _scrape_screenloop

        sl = _SCREENLOOP_PATTERN.search(url)
        if sl is None:
            raise ValueError(f"Not a Screenloop URL: {url}")
        return _scrape_screenloop(sl.group(1), sl.group(2))

    @property
    def priority(self) -> int:
        return 10


# Auto-register all ATS adapters
JobSourceRegistry.register(GreenhouseAdapter())
JobSourceRegistry.register(LeverAdapter())
JobSourceRegistry.register(AshbyAdapter())
JobSourceRegistry.register(WorkableAdapter())
JobSourceRegistry.register(PersonioAdapter())
JobSourceRegistry.register(ScreenloopAdapter())
