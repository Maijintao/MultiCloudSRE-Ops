import os
import shlex
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
FAULTS_DIR = ROOT / "faults"
CONFIG_FILE = ROOT / "config.json"
OUTPUT_FORMAT_FILE = ROOT / "output.md"
DEFAULT_SOUL_FILE = Path(os.environ.get("OJ_DEFAULT_SOUL_FILE", ROOT / "SOUL.md"))
STATE_DIR = ROOT / "state"
DB_FILE = Path(os.environ.get("OJ_DB_FILE", STATE_DIR / "oj.sqlite3"))
PLATFORM_SKILLS_DIR = ROOT / "runtime" / "platform-skills"

ENVIRONMENT = os.environ.get("OJ_ENV", "development").strip().lower() or "development"
IS_PRODUCTION = ENVIRONMENT in {"prod", "production"}


def require_production_env(name, default=""):
    value = os.environ.get(name, default)
    if IS_PRODUCTION and not str(value or "").strip():
        raise RuntimeError(f"{name} must be set when OJ_ENV=production")
    return value


PORT = int(os.environ.get("PORT", "8090"))
JWT_TTL_SECONDS = int(os.environ.get("OJ_JWT_TTL_SECONDS", str(2 * 24 * 3600)))
ADMIN_USERNAME = os.environ.get("OJ_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = require_production_env("OJ_ADMIN_PASSWORD", "dev-admin-password")
REGISTRATION_INVITE_CODE = require_production_env("OJ_REGISTRATION_INVITE_CODE", "dev-invite-code")
JWT_SECRET_ENV = require_production_env("OJ_JWT_SECRET", "")

DEFAULT_MODEL = os.environ.get("OJ_DEFAULT_MODEL", "gpt-4o-mini")
MODEL_CHECK_USER_AGENT = os.environ.get("OJ_MODEL_CHECK_USER_AGENT", "oj-platform/1.0")
GRADER_BASE_URL = require_production_env("OJ_GRADER_BASE_URL", "").strip().rstrip("/")
GRADER_MODEL = require_production_env("OJ_GRADER_MODEL", "").strip()
GRADER_API_KEY = require_production_env("OJ_GRADER_API_KEY", "").strip()
GRADER_LABEL = os.environ.get("OJ_GRADER_LABEL", "Platform grading API").strip() or "Platform grading API"
MAX_PROMPT_CHARS = int(os.environ.get("OJ_MAX_PROMPT_CHARS", "50000"))
MAX_SKILL_CHARS = int(os.environ.get("OJ_MAX_SKILL_CHARS", "100000"))
MAX_SKILLS = int(os.environ.get("OJ_MAX_SKILLS", "10"))
MAX_SOUL_CHARS = int(os.environ.get("OJ_MAX_SOUL_CHARS", "100000"))
MAX_SKILL_ARCHIVE_BYTES = int(os.environ.get("OJ_MAX_SKILL_ARCHIVE_BYTES", str(10 * 1024 * 1024)))
MAX_CASE_ARCHIVE_BYTES = int(os.environ.get("OJ_MAX_CASE_ARCHIVE_BYTES", str(10 * 1024 * 1024)))
MAX_SKILL_ARCHIVE_EXPANDED_BYTES = int(
    os.environ.get("OJ_MAX_SKILL_ARCHIVE_EXPANDED_BYTES", str(40 * 1024 * 1024))
)
MAX_SKILL_ARCHIVE_FILES = int(os.environ.get("OJ_MAX_SKILL_ARCHIVE_FILES", "1000"))
MAX_TRANSCRIPT_CHARS = int(os.environ.get("OJ_MAX_TRANSCRIPT_CHARS", "300000"))

AGENT_MAX_TURNS = os.environ.get("OJ_AGENT_MAX_TURNS", "40")
AGENT_TIMEOUT_SECONDS = int(os.environ.get("OJ_AGENT_TIMEOUT_SECONDS", "1800"))
JUDGE_TIMEOUT_SECONDS = int(os.environ.get("OJ_JUDGE_TIMEOUT_SECONDS", "900"))
FAULT_SCRIPT_TIMEOUT_SECONDS = int(os.environ.get("OJ_FAULT_SCRIPT_TIMEOUT_SECONDS", "300"))

HERMES_BIN = os.environ.get("HERMES_BIN", "hermes")
HERMES_PYTHON = os.environ.get("HERMES_PYTHON", "/usr/local/lib/hermes-agent/venv/bin/python")
HERMES_LIB = os.environ.get("HERMES_LIB", "/usr/local/lib/hermes-agent")
HERMES_UNATTENDED = os.environ.get("OJ_HERMES_UNATTENDED", "1") != "0"

HERMES_DOCKER_ENABLED = os.environ.get("OJ_HERMES_DOCKER", "1") != "0"
HERMES_DOCKER_IMAGE = os.environ.get("OJ_HERMES_DOCKER_IMAGE", "hermes-agent:latest")
HERMES_DOCKER_NETWORK = os.environ.get("OJ_HERMES_DOCKER_NETWORK", "bridge")
HERMES_DOCKER_CPUS = os.environ.get("OJ_HERMES_DOCKER_CPUS", "2")
HERMES_DOCKER_MEMORY = os.environ.get("OJ_HERMES_DOCKER_MEMORY", "2g")
HERMES_DOCKER_EXTRA_ARGS = shlex.split(os.environ.get("OJ_HERMES_DOCKER_EXTRA_ARGS", ""))
HERMES_CONTAINER_LIB = os.environ.get("OJ_HERMES_CONTAINER_LIB", "/opt/hermes-agent")
HERMES_CONTAINER_PYTHON = os.environ.get(
    "OJ_HERMES_CONTAINER_PYTHON",
    "/opt/hermes-agent/venv/bin/python",
)

GRADER_TOOLSETS_RAW = os.environ.get("OJ_GRADER_TOOLSETS", os.environ.get("OJ_HERMES_TOOLSETS", "terminal"))
HERMES_TOOLSETS_RAW = os.environ.get("OJ_HERMES_TOOLSETS", "terminal")

SENSITIVE_ENV_KEYS = {
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    "OPENAI_API_KEY",
    "CUSTOM_BASE_URL",
    "FAULT_TARGET_PASSWORD",
}

DIAGNOSTIC_INTENT_KEYWORDS = (
    "fault",
    "diagnose",
    "diagnosis",
    "troubleshoot",
    "root cause",
    "incident",
    "fix",
    "repair",
    "recover",
    "verify",
    "investigate",
    "failure",
    "outage",
)


def normalize_toolsets(value):
    items = []
    for raw_item in str(value or "").split(","):
        item = raw_item.strip()
        if not item:
            continue
        if item.lower() in {"mcp", "no_mcp"}:
            continue
        if item not in items:
            items.append(item)
    return ",".join(items or ["terminal"])


HERMES_TOOLSETS = normalize_toolsets(HERMES_TOOLSETS_RAW)
GRADER_TOOLSETS = normalize_toolsets(GRADER_TOOLSETS_RAW)
HERMES_TOOLSET_LIST = HERMES_TOOLSETS.split(",")
GRADER_TOOLSET_LIST = GRADER_TOOLSETS.split(",")
