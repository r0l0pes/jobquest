"""TypedDict schema for structured job posting data."""

from typing import TypedDict


class JobPost(TypedDict, total=False):
    """Structured job posting data.

    Required fields (always populated by scraping):
        title, company, description, url, source, questions

    Optional fields (populated by StructuredExtractor or downstream):
        salary_range, location, remote_policy, employment_type,
        department, required_skills, nice_to_have_skills, posted_date
    """

    # Required fields
    title: str
    company: str
    description: str
    url: str
    source: str
    questions: list[str]

    # Optional structured fields
    salary_range: str
    location: str
    remote_policy: str   # "fully_remote", "hybrid", "onsite", or ""
    employment_type: str  # "full_time", "contract", "part_time", or ""
    department: str
    required_skills: list[str]
    nice_to_have_skills: list[str]
    posted_date: str


def validate_job_post(data: dict) -> dict:
    """Lightweight validation: ensure required fields are present.

    Args:
        data: Dict to validate (from scraping or deserialization).

    Returns:
        The input dict (passed through for chaining).

    Raises:
        ValueError: If any required field is missing or empty.
    """
    required = ["title", "company", "url"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise ValueError(
            f"JobPost missing required fields: {', '.join(missing)}"
        )
    return data
