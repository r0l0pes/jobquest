"""Backward-compatibility shim for job scraper imports.

The original job_scraper.py (1,103 lines) has been split into:
  modules/scrapers/job_postings.py   — ATS APIs + generic scraping
  modules/scrapers/company_research.py — Company research + search

This file re-exports everything for backward compatibility.
Existing imports like `from modules.job_scraper import scrape_job_posting`
continue to work unchanged.
"""

from modules.scrapers.job_postings import scrape_job_posting
from modules.scrapers.company_research import research_company

__all__ = ["scrape_job_posting", "research_company"]
