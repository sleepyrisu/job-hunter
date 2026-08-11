import contextlib
import json
import os
from typing import Any

from dotenv import load_dotenv

# Load local environment variables from .env as a fallback
load_dotenv()

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

# Flask session / CSRF signing key. In production set a strong random value
# via SECRET_KEY env var; a stable local default keeps sessions valid across
# restarts on a single machine.
SECRET_KEY = os.getenv("SECRET_KEY", "ai-job-hunter-local-dev-key-change-me")

# Values that are just placeholders (never treated as real configuration)
PLACEHOLDER_MARKERS = ("your_", "dummy", "changeme", "replace", "xxx", "example.com")

# Module-level globals synced from settings.json by load_settings()/_sync_globals().
# Declared here (with defaults) so static analysis tools can see them.
API_KEY: str = ""
BASE_URL: str = ""
MODEL: str = ""
EMAIL_SENDER: str = ""
EMAIL_PASSWORD: str = ""
EMAIL_RECEIVER: str = ""
EMAIL_ENABLED: bool = False
SEARCH_KEYWORDS: list[str] = []
LOCATIONS: list[str] = []
MATCH_THRESHOLD: int = 50
DASHBOARD_TOKEN: str = ""


def is_placeholder(value):
    """Returns True if a value is empty or a non-functional placeholder."""
    if not value:
        return True
    return any(m in str(value).lower() for m in PLACEHOLDER_MARKERS)


# Default settings dict
_settings: dict[str, Any] = {
    "search": {
        "keywords": ["Data Analyst", "RPA Developer", "Python Developer", "C# Developer", "Junior Developer"],
        "locations": ["Penang, Malaysia", "Pulau Pinang"],
        "use_jobspy": True
    },
    "preferences": {
        "match_threshold": 80,
        # Legacy field kept for settings.json compatibility; the requirement
        # text (custom_requirements) is the single source of scoring preference.
        "company_type": "",
        "min_salary": 0,
        "max_age_days": 30,
        "safe_first": True,
        "use_ai": False,
        "custom_requirements": "基地在 Penang（槟城）。强烈偏好能提供明确调往 Kuala Lumpur (KL) "
                               "发展/轮岗/外派路径的岗位。MNC preferred."
    },
    "notifications": {
        "email_enabled": False,
        "email_sender": "",
        # Empty default; filled from settings.json or env at load time.
        "email_password": "",  # nosec B105
        "email_receiver": "",
        "telegram_enabled": False,
        "telegram_bot_token": "",
        "telegram_chat_id": ""
    },
    "ai": {
        "api_key": "",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "meta/llama-3.1-70b-instruct",
        "gemini_api_key": "",
        "gemini_model": "gemini-1.5-flash",
        "agnes_api_key": "",
        "agnes_base_url": "https://apihub.agnes-ai.com/v1",
        "agnes_model": "agnes-2.0-flash"
    },
    "scheduler": {
        "enabled": False,
        "interval_hours": 6,
        "next_run_at": None
    },
    "security": {
        # Empty default; set via env/settings at load time.
        "dashboard_token": ""  # nosec B105
    }
}

def load_settings() -> dict[str, Any]:
    """Loads settings from settings.json, overlaying env variables if present."""
    global _settings
    file_provided = set()  # dotted keys explicitly present in settings.json
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                data = json.load(f)
                # Deep merge defaults
                for section in _settings:
                    if section in data:
                        if isinstance(_settings[section], dict) and isinstance(data[section], dict):
                            for k in data[section]:
                                file_provided.add(f"{section}.{k}")
                            _settings[section].update(data[section])
                        else:
                            _settings[section] = data[section]
                            file_provided.add(section)
        except Exception as e:
            print(f"Error reading settings.json: {e}")

    # Normalize: values that are only placeholders should be treated as "not set",
    # so a real API key from .env can still take effect.
    if is_placeholder(_settings["ai"].get("api_key")):
        _settings["ai"]["api_key"] = ""
    if is_placeholder(_settings["ai"].get("gemini_api_key")):
        _settings["ai"]["gemini_api_key"] = ""

    # Override with Environment Variables ONLY IF the stored value is empty/placeholder.
    # This prevents .env from overwriting real user changes made via the Dashboard UI,
    # while still letting a real key replace leftover "dummy"/"your_api_key" placeholders.
    env_api_key = os.getenv("AI_API_KEY")
    if env_api_key and not _settings["ai"]["api_key"]:
        _settings["ai"]["api_key"] = env_api_key

    # Gemini is read from the dedicated gemini_api_key field.
    env_gemini_key = os.getenv("GEMINI_API_KEY")
    if env_gemini_key and not _settings["ai"].get("gemini_api_key"):
        _settings["ai"]["gemini_api_key"] = env_gemini_key

    env_base_url = os.getenv("AI_BASE_URL")
    if env_base_url and not _settings["ai"].get("base_url"):
        _settings["ai"]["base_url"] = env_base_url

    env_model = os.getenv("AI_MODEL")
    if env_model and not _settings["ai"].get("model"):
        _settings["ai"]["model"] = env_model

    # Agnes AI configuration
    env_agnes_key = os.getenv("AGNES_API_KEY")
    if env_agnes_key and not _settings["ai"].get("agnes_api_key"):
        _settings["ai"]["agnes_api_key"] = env_agnes_key

    env_agnes_url = os.getenv("AGNES_BASE_URL")
    if env_agnes_url:
        _settings["ai"]["agnes_base_url"] = env_agnes_url

    # Email credentials are secrets kept in .env; they always win over settings.json.
    env_sender = os.getenv("EMAIL_SENDER")
    if env_sender:
        _settings["notifications"]["email_sender"] = env_sender
        _settings["notifications"]["email_enabled"] = True

    env_password = os.getenv("EMAIL_PASSWORD")
    if env_password:
        _settings["notifications"]["email_password"] = env_password

    env_receiver = os.getenv("EMAIL_RECEIVER")
    if env_receiver:
        _settings["notifications"]["email_receiver"] = env_receiver

    env_keywords = os.getenv("SEARCH_KEYWORDS")
    if env_keywords and not _settings["search"]["keywords"]:
        _settings["search"]["keywords"] = [k.strip() for k in env_keywords.split(",") if k.strip()]

    env_locations = os.getenv("LOCATIONS")
    if env_locations and not _settings["search"]["locations"]:
        _settings["search"]["locations"] = [item.strip() for item in env_locations.split(",") if item.strip()]

    # MATCH_THRESHOLD env only acts as a fallback when settings.json doesn't define it,
    # so changes made through the Dashboard UI are not silently overwritten.
    env_threshold = os.getenv("MATCH_THRESHOLD")
    if env_threshold and "preferences.match_threshold" not in file_provided:
        with contextlib.suppress(ValueError):
            _settings["preferences"]["match_threshold"] = int(env_threshold)

    # USE_AI: when false (default), the pipeline runs fully resume-driven without any AI.
    env_use_ai = os.getenv("USE_AI")
    if env_use_ai:
        _settings["preferences"]["use_ai"] = env_use_ai.strip().lower() in ("1", "true", "yes", "on")

    # Dashboard access token
    env_token = os.getenv("DASHBOARD_TOKEN")
    if env_token and not _settings["security"].get("dashboard_token"):
        _settings["security"]["dashboard_token"] = env_token

    _sync_globals()
    return _settings


def _sync_globals():
    """Sync module-level globals from _settings dict after load_settings()."""
    global API_KEY, BASE_URL, MODEL
    global EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER, EMAIL_ENABLED
    global SEARCH_KEYWORDS, LOCATIONS, MATCH_THRESHOLD
    global DASHBOARD_TOKEN
    API_KEY = _settings["ai"]["api_key"]
    BASE_URL = _settings["ai"]["base_url"]
    MODEL = _settings["ai"]["model"]
    EMAIL_SENDER = _settings["notifications"]["email_sender"]
    EMAIL_PASSWORD = _settings["notifications"]["email_password"]
    EMAIL_RECEIVER = _settings["notifications"]["email_receiver"]
    EMAIL_ENABLED = _settings["notifications"]["email_enabled"]
    SEARCH_KEYWORDS = _settings["search"]["keywords"]
    LOCATIONS = _settings["search"]["locations"]
    MATCH_THRESHOLD = _settings["preferences"]["match_threshold"]
    DASHBOARD_TOKEN = _settings["security"].get("dashboard_token", "")


# Initial load
load_settings()

def validate_config():
    """Validates that crucial configurations are set, prints warnings otherwise."""
    warnings: list[str] = []
    settings = load_settings()
    use_ai = settings["preferences"].get("use_ai", False)
    if not use_ai:
        return warnings
    key = settings["ai"]["api_key"]
    gemini = settings["ai"].get("gemini_api_key", "")
    agnes = settings["ai"].get("agnes_api_key", "")
    if not key and not gemini and not agnes:
        warnings.append(
            "WARNING: AI evaluation is enabled (use_ai=true) but no AI API key is set. "
            "Falling back to rule-based evaluation."
        )
    
    if settings["notifications"]["email_enabled"]:
        sender = settings["notifications"]["email_sender"]
        password = settings["notifications"]["email_password"]
        if is_placeholder(sender):
            warnings.append("WARNING: EMAIL_SENDER is not set but email notification is enabled.")
        if is_placeholder(password):
            warnings.append("WARNING: EMAIL_PASSWORD is not set but email notification is enabled.")
    
    return warnings
