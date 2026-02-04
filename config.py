import os
from dotenv import load_dotenv

load_dotenv()

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
