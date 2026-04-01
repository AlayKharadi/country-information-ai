"""
Central configuration for the Country Information AI Agent.

A value that is referenced from more than one place should live here.
If you need to change a model, a timeout, or similar configuration this is
the only file needs to be updated.
"""

# Gemini via Vertex AI (ADC)
GEMINI_MODEL: str = "gemini-2.5-flash"

# REST Countries API
COUNTRIES_API_BASE_URL: str = "https://restcountries.com/v3.1"
API_TIMEOUT_SECONDS: int = 10

# Agent's supported fields
# Complete list of fields the agent understands and can retrieve.
# Adding support for a new field means updating this list *and* the 
# _FIELD_MAP in tools.py.
SUPPORTED_FIELDS: list[str] = [
    "population",
    "capital",
    "currency",
    "languages",
    "area",
    "region",
    "subregion",
    "flag",
    "timezones",
    "borders",
]

# FastAPI
MAX_QUESTION_LENGTH: int = 500
