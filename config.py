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

# Role variant — set by web UI toggle, drives Q&A framing
# Options: "growth_pm" | "generalist"
ROLE_VARIANT = get_env("ROLE_VARIANT", "growth_pm")
