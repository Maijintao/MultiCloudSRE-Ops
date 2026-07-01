import json
import sqlite3
import threading

from . import db, settings
from .textutil import mask_api_key


GRADER_CONFIG_SETTING_KEY = "grader_config"
_LOCK = threading.Lock()


def _complete(profile):
    return bool(
        str(profile.get("api_base_url") or "").strip()
        and str(profile.get("api_key") or "").strip()
        and str(profile.get("model") or "").strip()
    )


def _public_profile(profile, include_secret=False):
    api_key = str(profile.get("api_key") or "").strip()
    return {
        "source": "platform",
        "configured": _complete(profile),
        "api_base_url": str(profile.get("api_base_url") or "").strip().rstrip("/"),
        "api_key": api_key if include_secret else "",
        "api_key_mask": str(profile.get("api_key_mask") or "").strip() or (mask_api_key(api_key) if api_key else ""),
        "model": str(profile.get("model") or "").strip(),
    }


def env_platform_grader_config(include_secret=False):
    return _public_profile(
        {
            "api_base_url": settings.GRADER_BASE_URL,
            "api_key": settings.GRADER_API_KEY,
            "api_key_mask": mask_api_key(settings.GRADER_API_KEY) if settings.GRADER_API_KEY else "",
            "model": settings.GRADER_MODEL,
        },
        include_secret=include_secret,
    )


def stored_platform_grader_config(include_secret=False):
    try:
        raw = db.get_setting(GRADER_CONFIG_SETTING_KEY, "")
    except sqlite3.Error:
        raw = ""
    if not raw:
        return _public_profile({}, include_secret=include_secret)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = {}
    if not isinstance(value, dict):
        value = {}
    return _public_profile(
        {
            "api_base_url": value.get("api_base_url") or value.get("base_url") or "",
            "api_key": value.get("api_key") or "",
            "api_key_mask": value.get("api_key_mask") or "",
            "model": value.get("model") or "",
        },
        include_secret=include_secret,
    )


def effective_platform_grader_config(include_secret=False):
    stored = stored_platform_grader_config(include_secret=include_secret)
    if stored["configured"]:
        return stored
    return env_platform_grader_config(include_secret=include_secret)


def save_platform_grader_config(profile):
    payload = _public_profile(profile, include_secret=True)
    if not payload["configured"]:
        raise ValueError("platform scoring API is not configured")
    stored = {
        "api_base_url": payload["api_base_url"],
        "api_key": payload["api_key"],
        "api_key_mask": payload["api_key_mask"] or mask_api_key(payload["api_key"]),
        "model": payload["model"],
    }
    with _LOCK:
        db.set_setting(GRADER_CONFIG_SETTING_KEY, json.dumps(stored, ensure_ascii=False))
    return stored_platform_grader_config(include_secret=False)
