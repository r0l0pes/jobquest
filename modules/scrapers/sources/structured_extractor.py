"""Structured extraction adapter — enriches scraped job posts.

Wraps the output of another JobDataSource adapter and extracts structured
fields (salary, skills, remote policy, etc.) from the raw description text
using Firecrawl /extract (preferred) or a local LLM call (fallback).
"""

import copy
import json
import os
import re

from .base import JobDataSource


class StructuredExtractor(JobDataSource):
    """Enriches a JobPost with structured fields via LLM extraction.

    Does NOT fetch URLs itself — acts as a decorator that wraps the output
    of another adapter. Call enrich() on an existing job dict rather than
    fetch() on a URL.
    """

    def __init__(self, inner_source: JobDataSource | None = None):
        self._inner = inner_source

    # ── JobDataSource interface (decorator-only) ──────────────────

    def can_resolve(self, url: str) -> bool:
        """This adapter doesn't resolve URLs independently."""
        return False

    def fetch(self, url: str) -> dict:
        """Should not be called directly — use enrich() instead."""
        raise NotImplementedError(
            "StructuredExtractor is a decorator — use enrich() on an "
            "existing job dict, not fetch() on a URL."
        )

    @property
    def priority(self) -> int:
        return 999  # Only used as post-processor, never for resolution

    # ── Enrichment logic ──────────────────────────────────────────

    def enrich(self, job: dict) -> dict:
        """Enrich a scraped job dict with structured fields.

        Returns a new dict with optional structured fields populated.
        Never fails — returns the original dict on any extraction error.

        Args:
            job: Raw job dict from scraping (must have 'description' key).

        Returns:
            Enriched dict with optional structured fields added.
        """
        enriched = copy.deepcopy(job)

        desc = enriched.get("description", "")
        if len(desc) < 100:
            return enriched  # Not enough text to extract from

        # Strategy 1: Firecrawl /extract (structured, reliable)
        firecrawl_key = os.getenv("FIRECRAWL_API_KEY", "")
        if firecrawl_key:
            try:
                result = self._extract_via_firecrawl(enriched.get("url", ""), desc)
                if result:
                    self._merge(enriched, result)
                    return enriched
            except Exception:
                pass  # Fall through to LLM

        # Strategy 2: Local LLM extraction
        try:
            result = self._extract_via_llm(desc)
            if result:
                self._merge(enriched, result)
        except Exception:
            pass  # Graceful degradation

        return enriched

    @staticmethod
    def _merge(enriched: dict, result: dict) -> None:
        """Merge structured fields into the enriched dict.

        Only sets keys that have truthy values from the extraction result.
        Preserves any existing values from the original dict.
        """
        structured_keys = {
            "salary_range", "remote_policy", "employment_type",
            "department", "required_skills", "nice_to_have_skills",
            "posted_date",
        }
        for key in structured_keys:
            val = result.get(key)
            if val:  # Only overwrite with truthy values
                enriched[key] = val

    # ── Extraction strategies ─────────────────────────────────────

    def _extract_via_firecrawl(self, url: str, description: str) -> dict | None:
        """Use Firecrawl's /extract endpoint with a structured schema.

        Returns None if Firecrawl is unavailable or fails.
        """
        try:
            from firecrawl import FirecrawlApp
        except ImportError:
            return None

        try:
            api_key = os.getenv("FIRECRAWL_API_KEY")
            if not api_key:
                return None
            app = FirecrawlApp(api_key=api_key)
            extraction_schema = {
                "type": "object",
                "properties": {
                    "salary_range": {
                        "type": "string",
                        "description": "Salary range if mentioned in the posting",
                    },
                    "remote_policy": {
                        "type": "string",
                        "enum": ["fully_remote", "hybrid", "onsite"],
                        "description": "Remote work policy",
                    },
                    "employment_type": {
                        "type": "string",
                        "enum": ["full_time", "contract", "part_time"],
                        "description": "Employment type",
                    },
                    "department": {
                        "type": "string",
                        "description": "Department or team name",
                    },
                    "required_skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required skills explicitly listed",
                    },
                    "nice_to_have_skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Nice-to-have or preferred skills",
                    },
                },
            }
            doc = app.extract(
                [url],
                {
                    "prompt": "Extract structured job details from this posting.",
                    "schema": extraction_schema,
                },
            )
            if doc and isinstance(doc, dict) and doc.get("data"):
                return doc["data"]
        except Exception:
            pass
        return None

    def _extract_via_llm(self, description: str) -> dict | None:
        """Use a local LLM call to extract structured fields from the description.

        Returns None if the LLM call fails or returns unparseable output.
        """
        try:
            from modules.llm_client import create_ats_client
        except ImportError:
            return None

        try:
            client = create_ats_client()

            prompt = (
                f'Extract structured fields from this job description. '
                f'Return ONLY valid JSON.\n\n'
                f'{{\n'
                f'  "salary_range": "salary range if mentioned, empty string otherwise",\n'
                f'  "remote_policy": "fully_remote, hybrid, or onsite",\n'
                f'  "employment_type": "full_time, contract, or part_time",\n'
                f'  "department": "department name if mentioned, empty string otherwise",\n'
                f'  "required_skills": ["skill1", "skill2"],\n'
                f'  "nice_to_have_skills": ["skill1", "skill2"]\n'
                f'}}\n\n'
                f'Job Description:\n{description[:3000]}'
            )

            raw = client.generate(
                "You are a job posting parser. Extract structured data from "
                "job descriptions. Return only JSON.",
                prompt,
                temperature=0.1,
            )

            # Extract JSON from response (may be in code fence or bare)
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                parsed = json.loads(json_match.group(0))
                if isinstance(parsed, dict):
                    return parsed
        except Exception:
            pass
        return None
