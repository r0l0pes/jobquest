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
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
MASTER_RESUME_ID = os.getenv("NOTION_MASTER_RESUME_ID", "")
APPLICATIONS_DB_ID = os.getenv("NOTION_APPLICATIONS_DB_ID", "")
QA_TEMPLATES_DB_ID = os.getenv("NOTION_QA_TEMPLATES_DB_ID", "")
SKILLS_KEYWORDS_DB_ID = os.getenv("NOTION_SKILLS_KEYWORDS_DB_ID", "")

# LLM Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Applicant Info
APPLICANT_NAME = os.getenv("APPLICANT_NAME", "")
APPLICANT_EMAIL = os.getenv("APPLICANT_EMAIL", "")
APPLICANT_PHONE = os.getenv("APPLICANT_PHONE", "")
APPLICANT_LINKEDIN = os.getenv("APPLICANT_LINKEDIN", "")
APPLICANT_LOCATION = os.getenv("APPLICANT_LOCATION", "")

# Resume A/B Testing
# Options: "Tech-First" (Technical Proficiency before Experience), "Exp-First" (default)
RESUME_VARIANT = os.getenv("RESUME_VARIANT", "Tech-First")

# Role variant — set by web UI toggle, drives Q&A framing
# Options: "growth_pm" | "generalist"
ROLE_VARIANT = os.getenv("ROLE_VARIANT", "growth_pm")
