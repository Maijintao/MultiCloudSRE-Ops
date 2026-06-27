import unicodedata

from . import db, settings
from .skills import (
    SKILL_NAME_PATTERN,
    build_uploaded_archive_skill,
    profile_skills,
    public_skill_entry,
    remove_deleted_archives,
    skill_storage_fields,
)
from .soul import normalize_soul_markdown, soul_configured
from .security import hash_password
from .textutil import mask_api_key
from .timeutil import utc_now

MODEL_SOURCE_CUSTOM = "custom"
GRADER_SOURCE_PLATFORM = "platform"
USERNAME_MAX_LENGTH = 40
USERNAME_SPECIAL_CHARS = "._-"


def get_user_by_id(user_id):
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, username, role, disabled, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row or row["disabled"]:
            return None
        return db.row_to_dict(row)


def get_user_profile(user_id):
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT id, api_base_url, api_key, api_key_mask, model, skill, skills_json, soul_md,
                   grader_api_key, grader_api_key_mask
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    return db.row_to_dict(row)


def normalize_model_source(value):
    return MODEL_SOURCE_CUSTOM


def normalize_grader_source(value):
    return GRADER_SOURCE_PLATFORM


def custom_model_configured(profile):
    profile = profile or {}
    return bool(
        str(profile.get("api_base_url") or "").strip()
        and str(profile.get("api_key") or "").strip()
        and str(profile.get("model") or "").strip()
    )


def custom_grader_configured(profile):
    profile = profile or {}
    return bool(str(profile.get("grader_api_key") or "").strip())


def effective_model_profile(profile, include_secret=False):
    profile = profile or {}
    return {
        "source": MODEL_SOURCE_CUSTOM,
        "configured": custom_model_configured(profile),
        "api_base_url": str(profile.get("api_base_url") or "").strip(),
        "api_key": str(profile.get("api_key") or "").strip() if include_secret else "",
        "api_key_mask": profile.get("api_key_mask") or (mask_api_key(profile.get("api_key") or "") if profile.get("api_key") else ""),
        "model": str(profile.get("model") or "").strip(),
    }


def effective_grader_profile(profile, include_secret=False):
    configured = bool(settings.GRADER_BASE_URL and settings.GRADER_MODEL and settings.GRADER_API_KEY)
    api_key_mask = mask_api_key(settings.GRADER_API_KEY) if configured else ""
    return {
        "source": GRADER_SOURCE_PLATFORM,
        "configured": configured,
        "api_base_url": settings.GRADER_BASE_URL,
        "api_key": settings.GRADER_API_KEY if include_secret else "",
        "api_key_mask": api_key_mask,
        "model": settings.GRADER_MODEL,
    }


def public_user_profile(profile):
    profile = profile or {}
    effective = effective_model_profile(profile)
    effective_grader = effective_grader_profile(profile)
    skills = profile_skills(profile)
    soul_md = normalize_soul_markdown(profile.get("soul_md") or "")
    return {
        "model_source": MODEL_SOURCE_CUSTOM,
        "api_base_url": effective["api_base_url"],
        "model": effective["model"],
        "api_key_mask": effective["api_key_mask"],
        "configured": effective["configured"],
        "custom_configured": effective["configured"],
        "custom_api_base_url": effective["api_base_url"],
        "custom_model": effective["model"],
        "custom_api_key_mask": effective["api_key_mask"],
        "platform_model_available": False,
        "platform_model_label": "",
        "platform_api_base_url": "",
        "platform_model": "",
        "default_model": settings.DEFAULT_MODEL,
        "grader_source": GRADER_SOURCE_PLATFORM,
        "grader_base_url": effective_grader["api_base_url"],
        "grader_model": effective_grader["model"],
        "grader_api_key_mask": effective_grader["api_key_mask"],
        "grader_configured": effective_grader["configured"],
        "custom_grader_configured": False,
        "custom_grader_base_url": "",
        "custom_grader_model": "",
        "custom_grader_api_key_mask": "",
        "platform_grader_available": effective_grader["configured"],
        "platform_grader_label": settings.GRADER_LABEL,
        "platform_grader_base_url": effective_grader["api_base_url"],
        "platform_grader_model": effective_grader["model"],
        "soul_md": soul_md,
        "soul_configured": soul_configured(soul_md),
        "skills": [public_skill_entry(skill) for skill in skills],
    }


def public_admin_user(row):
    item = db.row_to_dict(row)
    return {
        "id": item["id"],
        "username": item["username"],
        "role": item["role"],
        "disabled": item["disabled"],
        "protected_admin": is_protected_admin_row(item),
        "created_at": item["created_at"],
        "password_status": "set",
    }


def public_session_user(row):
    item = db.row_to_dict(row)
    return {
        "id": item["id"],
        "username": item["username"],
        "role": item["role"],
        "disabled": item["disabled"],
        "created_at": item["created_at"],
        "profile_configured": public_user_profile(item)["configured"],
    }


def list_admin_users():
    with db.connect() as conn:
        return conn.execute(
            "SELECT id, username, role, disabled, created_at FROM users ORDER BY id"
        ).fetchall()


def normalize_username(username):
    return str(username or "").strip()


def protected_admin_username():
    return normalize_username(settings.ADMIN_USERNAME)


def is_protected_admin_row(row):
    if not row:
        return False
    return normalize_username(row["username"]) == protected_admin_username()


def username_char_allowed(char):
    if char in USERNAME_SPECIAL_CHARS:
        return True
    return unicodedata.category(char).startswith(("L", "N"))


def validate_username(username):
    username = normalize_username(username)
    if not 1 <= len(username) <= USERNAME_MAX_LENGTH:
        raise ValueError("用户名长度必须为 1 到 40 个字符")
    if not all(username_char_allowed(char) for char in username):
        raise ValueError("用户名仅支持中文、字母、数字、点号、下划线和连字符")
    return username


def validate_username_password(username, password):
    username = validate_username(username)
    if len(password) < 8:
        raise ValueError("password must be at least 8 chars")
    return username


def create_user(username, password, role="contestant"):
    username = validate_username_password(username, password)
    if role not in {"admin", "contestant"}:
        raise ValueError("invalid role")
    with db.connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (username, hash_password(password), role, utc_now()),
        )
        return cur.lastrowid


def update_admin_user(user_id, payload):
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, username, role, disabled, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            raise LookupError("user not found")
        if is_protected_admin_row(row) and any(key in payload for key in ("role", "disabled")):
            raise ValueError("built-in admin account role and status cannot be changed")
        fields = {}
        if "password" in payload and payload["password"]:
            password = str(payload["password"])
            if len(password) < 8:
                raise ValueError("password must be at least 8 chars")
            fields["password_hash"] = hash_password(password)
        if "role" in payload:
            role = str(payload["role"])
            if role not in {"admin", "contestant"}:
                raise ValueError("invalid role")
            fields["role"] = role
        if "disabled" in payload:
            fields["disabled"] = 1 if payload["disabled"] else 0
        if not fields:
            raise ValueError("nothing to update")
        assignments = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(f"UPDATE users SET {assignments} WHERE id = ?", list(fields.values()) + [user_id])
        return conn.execute(
            "SELECT id, username, role, disabled, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def update_user_profile_fields(user_id, fields):
    assignments = ", ".join(f"{key} = ?" for key in fields)
    with db.connect() as conn:
        conn.execute(f"UPDATE users SET {assignments} WHERE id = ?", list(fields.values()) + [user_id])
    return get_user_profile(user_id)


def update_user_skill_profile(user_id, raw_skills):
    existing_profile = get_user_profile(user_id)
    existing_skills = profile_skills(existing_profile)
    fields = skill_storage_fields(raw_skills, existing_skills=existing_skills)
    profile = update_user_profile_fields(
        user_id,
        {
            "skill": fields["skill"],
            "skills_json": fields["skills_json"],
        },
    )
    remove_deleted_archives(existing_skills, fields["skills"])
    return profile


def update_user_soul_profile(user_id, soul_md):
    return update_user_profile_fields(
        user_id,
        {
            "soul_md": normalize_soul_markdown(soul_md),
        },
    )


def delete_admin_user(user_id):
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            raise LookupError("user not found")
        if is_protected_admin_row(row):
            raise ValueError("built-in admin account cannot be deleted")
        if row["role"] == "admin":
            admin_count = conn.execute(
                "SELECT COUNT(*) AS n FROM users WHERE role = 'admin'"
            ).fetchone()["n"]
            if admin_count <= 1:
                raise ValueError("cannot delete the last admin user")
        active_submissions = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM submissions
            WHERE user_id = ?
              AND status NOT IN ('queued', 'done', 'failed')
            """,
            (user_id,),
        ).fetchone()["n"]
        if active_submissions:
            raise ValueError("cannot delete user while they have active submissions")
        deleted_submissions = conn.execute(
            "DELETE FROM submissions WHERE user_id = ?",
            (user_id,),
        ).rowcount or 0
        deleted_users = conn.execute(
            "DELETE FROM users WHERE id = ?",
            (user_id,),
        ).rowcount or 0
        if deleted_users != 1:
            raise RuntimeError("failed to delete user")
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "deleted_submissions": deleted_submissions,
        }


def upload_user_archive_skill(user_id, filename, archive_bytes):
    existing_profile = get_user_profile(user_id)
    existing_skills = profile_skills(existing_profile)
    if len(existing_skills) >= settings.MAX_SKILLS:
        raise ValueError(f"skills can contain at most {settings.MAX_SKILLS} items")
    archive_skill = build_uploaded_archive_skill(user_id, filename, archive_bytes)
    fields = skill_storage_fields(existing_skills + [archive_skill], existing_skills=existing_skills + [archive_skill])
    return update_user_profile_fields(
        user_id,
        {
            "skill": fields["skill"],
            "skills_json": fields["skills_json"],
        },
    )


def profile_fields(base_url, api_key, model):
    return {
        "api_base_url": base_url,
        "api_key": api_key,
        "api_key_mask": mask_api_key(api_key),
        "model": model,
    }
