"""Loads configuration from the .env file and exposes it as simple constants."""

import os
from dotenv import load_dotenv

load_dotenv()


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _list(value):
    return [x.strip() for x in (value or "").split(",") if x.strip()]


# --- GitLab ---
GITLAB_URL = os.environ.get("GITLAB_URL", "").rstrip("/")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
PROJECT_IDS = _list(os.environ.get("PROJECT_IDS"))
# Job names to ignore (e.g. noisy allow_failure jobs like sonarqube-check).
EXCLUDE_JOBS = _list(os.environ.get("EXCLUDE_JOBS"))
# GitLab user IDs whose repos should ALSO be monitored (team coverage).
# The tool watches the union of your repos + these members' repos.
TEAM_MEMBER_IDS = _list(os.environ.get("TEAM_MEMBER_IDS"))

# --- Polling ---
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "180"))
# 0 = scan ALL member projects every cycle (correct, recommended).
# >0 = only scan projects active within N hours (optimization; can MISS
#      failures when a pipeline is run without a fresh push, so keep 0).
ACTIVITY_WINDOW_HOURS = int(os.environ.get("ACTIVITY_WINDOW_HOURS", "0"))

# --- Ollama ---
# Set AI_ENABLED=false to skip the LLM entirely and email the raw log tail only
# (Ollama is left untouched so other tools can still use it).
AI_ENABLED = _bool(os.environ.get("AI_ENABLED"), True)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "600"))

# --- Email ---
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.example.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USE_TLS = _bool(os.environ.get("SMTP_USE_TLS"), True)
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
EMAIL_TO = _list(os.environ.get("EMAIL_TO"))

# --- Misc ---
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
LOG_FILE = os.environ.get("LOG_FILE", "ci_analyzer.log")
LOG_MAX_CHARS = int(os.environ.get("LOG_MAX_CHARS", "12000"))


def missing_required():
    """Return a list of config keys that must be filled in before the tool can run."""
    problems = []
    if not GITLAB_URL:
        problems.append("GITLAB_URL")
    if not GITLAB_TOKEN:
        problems.append("GITLAB_TOKEN")
    if not SMTP_PASSWORD:
        problems.append("SMTP_PASSWORD")
    if not EMAIL_TO:
        problems.append("EMAIL_TO")
    return problems
