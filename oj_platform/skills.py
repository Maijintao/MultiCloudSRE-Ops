import io
import json
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from . import settings
from .mcp import RUM2_MCP_SERVER_NAME
from .timeutil import utc_now


SKILL_KIND_TEXT = "text"
SKILL_KIND_ARCHIVE = "archive"
SKILL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SKILL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{5,63}$")
RUM2_PLATFORM_SKILL_NAME = "PLATFORM_RUM2_GUIDE"
RUM2_PLATFORM_SKILL_DIR = "tencent-cloud-rum"


def make_skill_id(prefix="skill"):
    return f"{prefix}-{uuid4().hex[:12]}"


def skills_archive_root():
    return settings.STATE_DIR / "skill_archives"


def _normalize_skill_id(value, index, name):
    raw = str(value or "").strip()
    if SKILL_ID_PATTERN.fullmatch(raw):
        return raw
    slug = _slugify_skill_name(name, fallback=f"skill-{index}")
    return f"{slug[:48]}-{index}"


def _slugify_skill_name(value, fallback="skill"):
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    text = text.strip(".-_")
    if not text or not text[0].isalnum():
        text = fallback
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text)
    text = text[:64].strip(".-_")
    if not text or not text[0].isalnum():
        text = fallback
    return text[:64]


def suggested_skill_name(value, fallback="SKILL1"):
    name = _slugify_skill_name(Path(str(value or "")).stem or value, fallback=fallback)
    if not SKILL_NAME_PATTERN.fullmatch(name):
        name = _slugify_skill_name(fallback, fallback="SKILL1")
    return name[:64]


def _unique_skill_name(value, index, used_names):
    fallback = suggested_skill_name(f"SKILL{index}", fallback="SKILL1")
    candidate = str(value or "").strip()
    if not SKILL_NAME_PATTERN.fullmatch(candidate):
        candidate = suggested_skill_name(candidate, fallback=fallback)
    if not candidate or not SKILL_NAME_PATTERN.fullmatch(candidate):
        candidate = fallback
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate
    suffix = 2
    while True:
        tail = f"-{suffix}"
        base = candidate[: max(1, 64 - len(tail))].rstrip(".-_")
        if not base or not base[0].isalnum():
            base = fallback[: max(1, 64 - len(tail))].rstrip(".-_") or fallback
        deduped = f"{base}{tail}"
        if SKILL_NAME_PATTERN.fullmatch(deduped) and deduped not in used_names:
            used_names.add(deduped)
            return deduped
        suffix += 1


def _state_relative_path(value):
    relpath = str(value or "").replace("\\", "/").strip().strip("/")
    if not relpath:
        raise ValueError("skill archive path is missing")
    target = (settings.STATE_DIR / relpath).resolve()
    try:
        target.relative_to(settings.STATE_DIR.resolve())
    except ValueError as exc:
        raise ValueError("skill archive path is invalid") from exc
    return relpath, target


def _archive_public_fields(skill):
    return {
        "id": skill["id"],
        "type": SKILL_KIND_ARCHIVE,
        "name": skill["name"],
        "source_name": skill.get("source_name", ""),
        "file_count": int(skill.get("file_count", 0) or 0),
        "archive_size": int(skill.get("archive_size", 0) or 0),
        "stored_at": skill.get("stored_at", ""),
    }


def public_skill_entry(skill):
    if skill.get("type") == SKILL_KIND_ARCHIVE:
        return _archive_public_fields(skill)
    return {
        "id": skill["id"],
        "type": SKILL_KIND_TEXT,
        "name": skill["name"],
        "content": skill.get("content", ""),
    }


def _validate_skill_list(skills):
    if len(skills) > settings.MAX_SKILLS:
        raise ValueError(f"skills can contain at most {settings.MAX_SKILLS} items")
    names = [item["name"] for item in skills]
    if len(names) != len(set(names)):
        raise ValueError("skill names must be unique")
    ids = [item["id"] for item in skills]
    if len(ids) != len(set(ids)):
        raise ValueError("skill ids must be unique")
    skill_text = "\n\n".join(
        f"## {item['name']}\n\n{item['content']}"
        for item in skills
        if item.get("type") != SKILL_KIND_ARCHIVE
    )
    if len(skill_text) > settings.MAX_SKILL_CHARS:
        raise ValueError(f"skills are too long, max {settings.MAX_SKILL_CHARS} chars total")
    return skill_text


def serialize_skill_fields(skills):
    skill_text = _validate_skill_list(skills)
    serialized = []
    for skill in skills:
        if skill.get("type") == SKILL_KIND_ARCHIVE:
            relpath, _ = _state_relative_path(skill.get("storage_relpath"))
            serialized.append(
                {
                    **_archive_public_fields(skill),
                    "storage_relpath": relpath,
                }
            )
        else:
            serialized.append(
                {
                    "id": skill["id"],
                    "type": SKILL_KIND_TEXT,
                    "name": skill["name"],
                    "content": skill.get("content", ""),
                }
            )
    return {
        "skills": skills,
        "skill": skill_text,
        "skills_json": json.dumps(serialized, ensure_ascii=False),
    }


def normalize_stored_skill_entries(raw_skills):
    if raw_skills is None:
        return []
    if not isinstance(raw_skills, list):
        raise ValueError("skills must be a list")
    skills = []
    used_names = set()
    for index, item in enumerate(raw_skills, start=1):
        if isinstance(item, dict):
            kind = SKILL_KIND_ARCHIVE if str(item.get("type") or "").strip().lower() == SKILL_KIND_ARCHIVE else SKILL_KIND_TEXT
            if kind == SKILL_KIND_ARCHIVE:
                name = _unique_skill_name(item.get("name", "") or f"SKILL{index}", index, used_names)
                skill_id = _normalize_skill_id(item.get("id"), index, name)
                relpath, _ = _state_relative_path(item.get("storage_relpath"))
                skills.append(
                    {
                        "id": skill_id,
                        "type": SKILL_KIND_ARCHIVE,
                        "name": name,
                        "source_name": str(item.get("source_name") or "").strip(),
                        "file_count": int(item.get("file_count", 0) or 0),
                        "archive_size": int(item.get("archive_size", 0) or 0),
                        "stored_at": str(item.get("stored_at") or "").strip(),
                        "storage_relpath": relpath,
                    }
                )
                continue
            content = str(item.get("content", "") or "").strip()
        else:
            content = str(item or "").strip()
        if not content:
            continue
        name = _unique_skill_name(
            item.get("name", "") if isinstance(item, dict) else f"SKILL{index}",
            index,
            used_names,
        )
        skill_id = _normalize_skill_id(item.get("id") if isinstance(item, dict) else "", index, name)
        skills.append(
            {
                "id": skill_id,
                "type": SKILL_KIND_TEXT,
                "name": name,
                "content": content,
            }
        )
    _validate_skill_list(skills)
    return skills


def normalize_skill_entries(raw_skills, existing_skills=None):
    if raw_skills is None:
        return []
    if not isinstance(raw_skills, list):
        raise ValueError("skills must be a list")
    existing_by_id = {skill["id"]: skill for skill in normalize_stored_skill_entries(existing_skills or [])}
    skills = []
    used_names = set()
    for index, item in enumerate(raw_skills, start=1):
        if isinstance(item, dict):
            kind = SKILL_KIND_ARCHIVE if str(item.get("type") or "").strip().lower() == SKILL_KIND_ARCHIVE else SKILL_KIND_TEXT
            if kind == SKILL_KIND_ARCHIVE:
                name = _unique_skill_name(item.get("name", "") or f"SKILL{index}", index, used_names)
                skill_id = _normalize_skill_id(item.get("id"), index, name)
                archived = existing_by_id.get(skill_id)
                if not archived or archived.get("type") != SKILL_KIND_ARCHIVE:
                    raise ValueError("archive skill must be uploaded before it can be saved")
                skills.append({**archived, "name": name})
                continue
            content = str(item.get("content", "") or "").strip()
        else:
            content = str(item or "").strip()
        if not content:
            continue
        name = _unique_skill_name(
            item.get("name", "") if isinstance(item, dict) else f"SKILL{index}",
            index,
            used_names,
        )
        skill_id = _normalize_skill_id(item.get("id") if isinstance(item, dict) else "", index, name)
        skills.append(
            {
                "id": skill_id,
                "type": SKILL_KIND_TEXT,
                "name": name,
                "content": content,
            }
        )
    _validate_skill_list(skills)
    return skills


def skill_storage_fields(raw_skills, existing_skills=None):
    return serialize_skill_fields(normalize_skill_entries(raw_skills, existing_skills=existing_skills))


def profile_skills(profile):
    profile = profile or {}
    raw_json = str(profile.get("skills_json") or "").strip()
    if raw_json:
        try:
            return normalize_stored_skill_entries(json.loads(raw_json))
        except Exception:
            pass
    legacy_skill = str(profile.get("skill") or "").strip()
    return (
        [
            {
                "id": _normalize_skill_id("", 1, "SKILL1"),
                "type": SKILL_KIND_TEXT,
                "name": "SKILL1",
                "content": legacy_skill,
            }
        ]
        if legacy_skill
        else []
    )


def selected_profile_skills(skills, skill_ids):
    selected_refs = []
    for raw_id in skill_ids or []:
        skill_ref = str(raw_id or "").strip()
        if not skill_ref:
            continue
        if len(skill_ref) > 64:
            raise ValueError("invalid skill selection")
        if skill_ref not in selected_refs:
            selected_refs.append(skill_ref)
    if len(selected_refs) > settings.MAX_SKILLS:
        raise ValueError(f"can select at most {settings.MAX_SKILLS} skills")
    if not selected_refs:
        return []
    skills_by_id = {skill["id"]: skill for skill in skills}
    skills_by_name = {skill["name"]: skill for skill in skills}
    matched = []
    missing = []
    seen = set()
    for skill_ref in selected_refs:
        skill = skills_by_id.get(skill_ref) or skills_by_name.get(skill_ref)
        if not skill:
            missing.append(skill_ref)
            continue
        if skill["id"] in seen:
            continue
        seen.add(skill["id"])
        matched.append(skill)
    if missing:
        raise ValueError("selected skill is no longer available, refresh and try again")
    return matched


def _zip_members(zip_file):
    members = []
    total_size = 0
    for info in zip_file.infolist():
        raw_name = str(info.filename or "").replace("\\", "/")
        if not raw_name or raw_name.endswith("/"):
            continue
        path = PurePosixPath(raw_name)
        parts = [part for part in path.parts if part not in ("", ".")]
        if not parts or parts[0] == "__MACOSX":
            continue
        if path.is_absolute() or any(part == ".." for part in parts):
            raise ValueError("zip archive contains an invalid path")
        if info.flag_bits & 0x1:
            raise ValueError("encrypted zip archives are not supported")
        total_size += int(info.file_size or 0)
        members.append((info, parts))
    if not members:
        raise ValueError("zip archive must contain at least one file")
    if len(members) > settings.MAX_SKILL_ARCHIVE_FILES:
        raise ValueError(f"zip archive can contain at most {settings.MAX_SKILL_ARCHIVE_FILES} files")
    if total_size > settings.MAX_SKILL_ARCHIVE_EXPANDED_BYTES:
        raise ValueError(f"zip archive is too large after extraction, max {settings.MAX_SKILL_ARCHIVE_EXPANDED_BYTES} bytes")
    return members


def _common_prefix(parts_list):
    if not parts_list:
        return []
    prefix = list(parts_list[0])
    for parts in parts_list[1:]:
        limit = min(len(prefix), len(parts))
        index = 0
        while index < limit and prefix[index] == parts[index]:
            index += 1
        prefix = prefix[:index]
        if not prefix:
            break
    if prefix and all(len(parts) > len(prefix) for parts in parts_list):
        return prefix
    return []


def _safe_rmtree(relpath):
    if not relpath:
        return
    _, target = _state_relative_path(relpath)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)


def _extract_zip_to_dir(archive_bytes, target_dir):
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zip_file:
        members = _zip_members(zip_file)
        common_prefix = _common_prefix([parts for _, parts in members])
        for info, parts in members:
            stripped = parts[len(common_prefix):] if common_prefix else parts
            rel_parts = stripped or [parts[-1]]
            target_path = (target_dir / Path(*rel_parts)).resolve()
            try:
                target_path.relative_to(target_dir.resolve())
            except ValueError as exc:
                raise ValueError("zip archive contains an invalid target path") from exc
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(info, "r") as source, target_path.open("wb") as output:
                shutil.copyfileobj(source, output)
    return members


def build_uploaded_archive_skill(user_id, filename, archive_bytes):
    data = bytes(archive_bytes or b"")
    if not filename:
        raise ValueError("zip filename is required")
    if not str(filename).lower().endswith(".zip"):
        raise ValueError("skill upload must be a .zip file")
    if not data:
        raise ValueError("zip archive is empty")
    if len(data) > settings.MAX_SKILL_ARCHIVE_BYTES:
        raise ValueError(f"zip archive is too large, max {settings.MAX_SKILL_ARCHIVE_BYTES} bytes")
    skill_id = make_skill_id("skill")
    relpath = f"skill_archives/users/{user_id}/{skill_id}"
    _, target_dir = _state_relative_path(relpath)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    try:
        members = _extract_zip_to_dir(data, target_dir)
    except zipfile.BadZipFile as exc:
        raise ValueError("invalid zip archive") from exc
    except Exception:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        raise
    return {
        "id": skill_id,
        "type": SKILL_KIND_ARCHIVE,
        "name": suggested_skill_name(filename, fallback=f"SKILL{user_id}"),
        "source_name": Path(str(filename)).name,
        "file_count": len(members),
        "archive_size": len(data),
        "stored_at": utc_now(),
        "storage_relpath": relpath,
    }


def snapshot_submission_skills(skills):
    normalized = normalize_stored_skill_entries(skills or [])
    if not normalized:
        return serialize_skill_fields([])
    snapshot_token = make_skill_id("submission")
    archived = []
    for skill in normalized:
        if skill.get("type") != SKILL_KIND_ARCHIVE:
            archived.append(dict(skill))
            continue
        _, source_dir = _state_relative_path(skill.get("storage_relpath"))
        if not source_dir.exists():
            raise ValueError(f"archive skill '{skill['name']}' is missing, please re-upload it")
        relpath = f"skill_archives/submissions/{snapshot_token}/{skill['id']}"
        _, target_dir = _state_relative_path(relpath)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        shutil.copytree(source_dir, target_dir)
        archived.append({**skill, "storage_relpath": relpath})
    return serialize_skill_fields(archived)


def remove_deleted_archives(previous_skills, next_skills):
    previous_archives = {
        skill["id"]: skill.get("storage_relpath")
        for skill in normalize_stored_skill_entries(previous_skills or [])
        if skill.get("type") == SKILL_KIND_ARCHIVE
    }
    kept_archives = {
        skill["id"]
        for skill in normalize_stored_skill_entries(next_skills or [])
        if skill.get("type") == SKILL_KIND_ARCHIVE
    }
    for skill_id, relpath in previous_archives.items():
        if skill_id not in kept_archives:
            _safe_rmtree(relpath)


def _write_text_skill(skill_dir, skill_name, body):
    content = f"""---
name: {skill_name}
description: Contestant supplied diagnostic skill for this isolated OJ submission.
version: 1.0.0
author: OJ Contestant
license: Unspecified
metadata:
  hermes:
    tags: [oj, contestant, evaluation]
---

# {skill_name}

{body}
"""
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def _write_archive_skill(skill_dir, skill):
    _, source_dir = _state_relative_path(skill.get("storage_relpath"))
    if not source_dir.exists():
        raise ValueError(f"archive skill '{skill['name']}' is missing, please re-upload it")
    shutil.copytree(source_dir, skill_dir, dirs_exist_ok=True)
    if not (skill_dir / "SKILL.md").exists():
        content = f"""---
name: {skill['name']}
description: Uploaded contestant skill files for this isolated OJ submission.
version: 1.0.0
author: OJ Contestant
license: Unspecified
metadata:
  hermes:
    tags: [oj, contestant, evaluation, archive]
---

# {skill['name']}

Inspect the files in this skill directory and use them when they help with diagnosis or recovery.
"""
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def write_platform_skills(home, toolsets):
    if RUM2_MCP_SERVER_NAME not in set(toolsets or []):
        return []
    source_dir = settings.PLATFORM_SKILLS_DIR / RUM2_PLATFORM_SKILL_DIR
    if not source_dir.is_dir() or not (source_dir / "SKILL.md").is_file():
        raise ValueError("RUM2 platform skill is missing")
    target_dir = home / "skills" / RUM2_PLATFORM_SKILL_NAME
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir)
    return [RUM2_PLATFORM_SKILL_NAME]


def write_contestant_skills(home, skill_text, skills_json, reserved_names=None):
    if skills_json:
        try:
            skills = normalize_stored_skill_entries(json.loads(skills_json))
        except Exception as exc:
            raise ValueError(f"invalid submission skills: {exc}") from exc
    else:
        legacy = str(skill_text or "").strip()
        skills = (
            [
                {
                    "id": _normalize_skill_id("", 1, "SKILL1"),
                    "type": SKILL_KIND_TEXT,
                    "name": "SKILL1",
                    "content": legacy,
                }
            ]
            if legacy
            else []
        )
    if not skills:
        return ""
    names = []
    used_names = set(reserved_names or [])
    for index, skill in enumerate(skills, start=1):
        requested_name = str(skill.get("name") or "").strip() or f"SKILL{index}"
        skill_name = requested_name if SKILL_NAME_PATTERN.fullmatch(requested_name) else f"SKILL{index}"
        if skill_name in used_names:
            suffix = index
            while f"SKILL{suffix}" in used_names:
                suffix += 1
            skill_name = f"SKILL{suffix}"
        used_names.add(skill_name)
        skill_dir = home / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        if skill.get("type") == SKILL_KIND_ARCHIVE:
            _write_archive_skill(skill_dir, skill)
        else:
            _write_text_skill(skill_dir, skill_name, skill.get("content", ""))
        names.append(skill_name)
    return ",".join(names)
