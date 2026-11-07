"""Central settings for the Student Grade Portal.

Every value can be overridden with an environment variable (or a `.env` file),
which keeps secrets and machine specific paths out of the source code.
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _flag(name, default="0"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


# ---------------------------- environment ----------------------------
ENV = os.environ.get("SGP_ENV", "development").strip().lower()
IS_PRODUCTION = ENV == "production"
DEBUG = _flag("SGP_DEBUG", "0" if IS_PRODUCTION else "1")

SECRET_KEY = os.environ.get("SGP_SECRET_KEY", "dev-secret-change-me")

# ------------------------------ files -------------------------------
DB_NAME = os.environ.get("SGP_DB_NAME", os.path.join(BASE_DIR, "students.db"))
CSV_FILE = os.environ.get("SGP_CSV_FILE", os.path.join(BASE_DIR, "student_records.csv"))
LOG_FILE = os.environ.get("SGP_LOG_FILE", os.path.join(BASE_DIR, "app.log"))
LOG_LEVEL = os.environ.get("SGP_LOG_LEVEL", "INFO").upper()

# ----------------------------- session ------------------------------
SESSION_LIFETIME_MINUTES = _int("SGP_SESSION_MINUTES", 60)
SESSION_COOKIE_SECURE = _flag("SGP_COOKIE_SECURE", "1" if IS_PRODUCTION else "0")

# -------------------------- login lockout ---------------------------
LOGIN_MAX_ATTEMPTS = _int("SGP_LOGIN_MAX_ATTEMPTS", 5)
LOGIN_LOCKOUT_SECONDS = _int("SGP_LOGIN_LOCKOUT_SECONDS", 300)

# ----------------------------- grading ------------------------------
SUBJECTS = ["Maths", "Physics", "Chemistry", "English", "Computer"]

MAX_MARK = 50

PASS_MARK = 20

GRADE_SCALE = [
    (90, "A+"),
    (80, "A"),
    (70, "B+"),
    (60, "B"),
    (50, "C"),
    (40, "D"),
]

# ------------------------- registration numbers ---------------------
REG_PREFIX = "SGP"

REG_START_MIN = 1000

REG_START_MAX = 9000

# ------------------------------ paging ------------------------------
PAGE_SIZE = _int("SGP_PAGE_SIZE", 10)

# ------------------------------ email -------------------------------
# Used by the optional "email report card" feature. Leave disabled unless
# SMTP details are provided.
MAIL_ENABLED = _flag("SGP_MAIL_ENABLED", "0")
MAIL_SERVER = os.environ.get("SGP_MAIL_SERVER", "")
MAIL_PORT = _int("SGP_MAIL_PORT", 587)
MAIL_USERNAME = os.environ.get("SGP_MAIL_USERNAME", "")
MAIL_PASSWORD = os.environ.get("SGP_MAIL_PASSWORD", "")
MAIL_SENDER = os.environ.get("SGP_MAIL_SENDER", "no-reply@student-grade-portal")

# ---------------------------- attendance ----------------------------
ATTENDANCE_STATUSES = ["present", "absent", "late"]

# ------------------------------ at-risk -----------------------------
# A student is flagged when their overall percentage or attendance dips
# below these thresholds, or when they fail a subject.
RISK_PERCENTAGE = _int("SGP_RISK_PERCENTAGE", 40)
RISK_ATTENDANCE = _int("SGP_RISK_ATTENDANCE", 75)

# ------------------------- terms and exams --------------------------
# Used by the term-wise marks / transcript feature.
TERMS = ["Term 1", "Term 2", "Term 3"]
EXAMS = ["Mid-Term", "Final"]

# ------------------------------- API --------------------------------
# When set, the JSON API accepts this value in the X-API-Token header.
# Database-issued API keys (api_keys table) are also accepted.
API_TOKEN = os.environ.get("SGP_API_TOKEN", "dev-api-token")

# -------------------------- rate limiting ---------------------------
RATE_LIMIT_ENABLED = _flag("SGP_RATE_LIMIT", "1")
LOGIN_RATE_LIMIT = _int("SGP_LOGIN_RATE_LIMIT", 20)      # attempts per minute per IP
API_RATE_LIMIT = _int("SGP_API_RATE_LIMIT", 120)          # requests per minute per IP

# ------------------------ security headers --------------------------
SECURITY_HEADERS = _flag("SGP_SECURITY_HEADERS", "1")

# Placeholder values that must never reach production.
DEFAULT_SECRET_KEY = "dev-secret-change-me"
DEFAULT_API_TOKEN = "dev-api-token"

# ---------------------------- permissions ---------------------------
PERMISSIONS = {
    "admin": [
        "add", "view", "search", "update", "delete", "export", "stats",
        "report", "import", "marks", "attendance", "audit", "users",
        "subjects", "archive", "transcripts", "email", "apikeys", "graderules",
        "risk",
    ],
    "faculty": [
        "add", "view", "search", "update", "export", "stats",
        "report", "import", "marks", "attendance", "transcripts", "email",
        "risk",
    ],
    "student": [
        "self",
    ],
}

# --------------------- default users (first run) --------------------
# Created automatically the first time the database is initialised.
# Change the passwords after the first login.
DEFAULT_USERS = [
    ("admin", "admin123", "admin"),
    ("faculty", "faculty123", "faculty"),
]


class ConfigurationError(RuntimeError):
    """Raised when the environment is unsafe to run in."""


def validate_config():
    """Refuse to start in production with the shipped placeholder secrets."""
    if not IS_PRODUCTION:
        return
    problems = []
    if SECRET_KEY == DEFAULT_SECRET_KEY:
        problems.append("SGP_SECRET_KEY is still the default value")
    if API_TOKEN == DEFAULT_API_TOKEN:
        problems.append("SGP_API_TOKEN is still the default value")
    if not SESSION_COOKIE_SECURE:
        problems.append("SGP_COOKIE_SECURE must be enabled in production")
    if problems:
        raise ConfigurationError(
            "Unsafe production configuration: " + "; ".join(problems)
        )
