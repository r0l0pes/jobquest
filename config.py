import os
from dotenv import load_dotenv

load_dotenv()


def get_env(name: str, default: str = "", required: bool = False) -> str:
    """Read an environment variable with validation.
    
    Args:
        name: Environment variable name
        default: Default value if not set
        required: If True, raise ValueError when value is empty/missing
        
    Returns:
        The environment variable value or default
        
    Raises:
        ValueError: If required=True and value is empty/missing
    """
    value = os.getenv(name, default)
    
    if required and not value:
        raise ValueError(
            f"Environment variable '{name}' is required but not set. "
            f"Add it to your .env file or set it in your environment."
        )
    
    return value

# Notion Configuration
NOTION_TOKEN = get_env("NOTION_TOKEN", "")
MASTER_RESUME_ID = get_env("NOTION_MASTER_RESUME_ID", "")
APPLICATIONS_DB_ID = get_env("NOTION_APPLICATIONS_DB_ID", "")
QA_TEMPLATES_DB_ID = get_env("NOTION_QA_TEMPLATES_DB_ID", "")
SKILLS_KEYWORDS_DB_ID = get_env("NOTION_SKILLS_KEYWORDS_DB_ID", "")

# LLM Configuration
GEMINI_API_KEY = get_env("GEMINI_API_KEY", "")

# Applicant Info
APPLICANT_NAME = get_env("APPLICANT_NAME", "")
APPLICANT_EMAIL = get_env("APPLICANT_EMAIL", "")
APPLICANT_PHONE = get_env("APPLICANT_PHONE", "")
APPLICANT_LINKEDIN = get_env("APPLICANT_LINKEDIN", "")
APPLICANT_LOCATION = get_env("APPLICANT_LOCATION", "")

# Resume A/B Testing
# Options: "Tech-First" (Technical Proficiency before Experience), "Exp-First" (default)
RESUME_VARIANT = get_env("RESUME_VARIANT", "Tech-First")

# Role variant — set by web UI toggle, drives tagline, Q&A framing, and AI context injection
# Options: "growth_pm" | "generalist" | "ai_pm"
ROLE_VARIANT = get_env("ROLE_VARIANT", "growth_pm")

# Per-step LLM model selectors (U1 — see docs/plans/2026-07-05-002-refactor-scraping-llm-seams-plan.md)
# Set PROVIDER + MODEL pair to override a specific pipeline step.
# Leave empty to use the default: tailor/QA use writing chain, reviewer uses Gemini,
# ATS uses Gemini fallback, interview uses Kimi K2.6 via OpenCode, fit uses Flash-Lite.
TAILOR_PROVIDER = get_env("TAILOR_PROVIDER", "")
TAILOR_MODEL = get_env("TAILOR_MODEL", "")
REVIEWER_PROVIDER = get_env("REVIEWER_PROVIDER", "")
REVIEWER_MODEL = get_env("REVIEWER_MODEL", "")
ATS_PROVIDER = get_env("ATS_PROVIDER", "")
ATS_MODEL = get_env("ATS_MODEL", "")
QA_PROVIDER = get_env("QA_PROVIDER", "")
QA_MODEL = get_env("QA_MODEL", "")
INTERVIEW_PROVIDER = get_env("INTERVIEW_PROVIDER", "")
INTERVIEW_MODEL = get_env("INTERVIEW_MODEL", "")
FIT_PROVIDER = get_env("FIT_PROVIDER", "")
FIT_MODEL = get_env("FIT_MODEL", "")

# Apify API Key for JobStream and other web scraping actors
APIFY_API_KEY = get_env("APIFY_API_KEY", "")
