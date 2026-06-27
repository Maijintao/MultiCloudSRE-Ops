import json
import time
import re
import uuid
from datetime import datetime, timedelta, timezone

from . import db, settings
from .cases import (
    case_set_id,
    is_training_case,
    is_test_set_case,
    is_ungrouped_case,
    load_cases_list,
    load_cases_map,
    load_public_cases_map,
    public_test_sets,
    public_case,
    test_set_by_id,
    test_set_members,
)
from .grading import verdict_for_score
from .hermes_transcript import answer_process_for_grading, extract_process_stderr, summarize_agent_failure
from .mcp import (
    ANSWER_MCP_SNAPSHOT_COLUMN,
    answer_mcp_servers as resolve_answer_mcp_servers,
    default_case_mcp_servers,
    dump_answer_mcp_servers_json,
    normalize_selected_public_mcp_servers,
    public_case_mcp_server_label,
)
from .skills import (
    SKILL_ID_PATTERN,
    SKILL_KIND_ARCHIVE,
    normalize_stored_skill_entries,
    selected_profile_skills,
    snapshot_submission_skills,
)
from .soul import normalize_soul_markdown
from .textutil import mask_api_key, truncate_text
from .timeutil import utc_now
from .users import (
    effective_grader_profile,
    effective_model_profile,
    get_user_profile,
    profile_skills,
    public_user_profile,
)


INTERRUPTED_STATUSES = ("running", "injecting", "answering", "recovering", "grading")
ADMIN_DELETABLE_SUBMISSION_STATUSES = {"queued", "done", "failed"}
CONTESTANT_DELETABLE_SUBMISSION_STATUSES = {"queued"}
RETRYABLE_SUBMISSION_STATUSES = {"done", "failed"}
DEFAULT_SUBMISSIONS_PER_PAGE = 20
MAX_SUBMISSIONS_PER_PAGE = 100
DEFAULT_LEADERBOARD_LIMIT = 100
BEIJING_TIMEZONE = timezone(timedelta(hours=8))
OVERNIGHT_QUEUE_LIMIT = 50
TEST_SET_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
TEST_SET_PLACEHOLDERS = {"fault_phenomenon", "public_case_info"}


def validate_submission_payload(payload):
    case_id = str(payload.get("case_id", "")).strip()
    prompt = str(payload.get("prompt", "")).strip()
    raw_skill_ids = payload.get("skill_ids")
    raw_mcp_servers = payload.get(ANSWER_MCP_SNAPSHOT_COLUMN) if ANSWER_MCP_SNAPSHOT_COLUMN in payload else payload.get("mcp_servers")
    if case_id not in load_cases_map():
        raise ValueError("unknown case")
    if not prompt:
        raise ValueError("prompt is required")
    if len(prompt) > settings.MAX_PROMPT_CHARS:
        raise ValueError(f"prompt is too long, max {settings.MAX_PROMPT_CHARS} chars")
    if raw_skill_ids is None:
        skill_ids = []
    elif not isinstance(raw_skill_ids, list):
        raise ValueError("skill_ids must be a list")
    else:
        skill_ids = []
        for item in raw_skill_ids:
            skill_ref = str(item or "").strip()
            if not skill_ref:
                continue
            if len(skill_ref) > 64:
                raise ValueError("invalid skill selection")
            if skill_ref not in skill_ids:
                skill_ids.append(skill_ref)
    if len(skill_ids) > settings.MAX_SKILLS:
        raise ValueError(f"can select at most {settings.MAX_SKILLS} skills")
    mcp_servers = normalize_selected_public_mcp_servers(raw_mcp_servers, default_to_all=True)
    return {
        "case_id": case_id,
        "prompt": prompt,
        "skill_ids": skill_ids,
        "mcp_servers": mcp_servers,
    }


def validate_test_set_submission_payload(payload):
    data = validate_submission_payload({**(payload or {}), "case_id": next(iter(load_cases_map()), "")})
    data.pop("case_id", None)
    placeholders = {name.strip() for name in TEST_SET_PLACEHOLDER_PATTERN.findall(data["prompt"])}
    unsupported = sorted(placeholders - TEST_SET_PLACEHOLDERS)
    if unsupported:
        raise ValueError(
            "unsupported placeholders: "
            + ", ".join(f"{{{{{name}}}}}" for name in unsupported)
            + "; supported placeholders are {{fault_phenomenon}} and {{public_case_info}}"
        )
    return data


def render_test_set_prompt(prompt, case):
    replacements = {
        "fault_phenomenon": str((case or {}).get("fault_phenomenon") or ""),
        "public_case_info": str((case or {}).get("public_case_info") or ""),
    }

    def replace(match):
        name = match.group(1).strip()
        return replacements[name]

    rendered = TEST_SET_PLACEHOLDER_PATTERN.sub(replace, prompt)
    if len(rendered) > settings.MAX_PROMPT_CHARS:
        raise ValueError(f"rendered prompt is too long, max {settings.MAX_PROMPT_CHARS} chars")
    return rendered


def case_submission_enabled(case):
    return bool((case or {}).get("submission_enabled", True))


def case_ai_analysis_visible(case):
    return bool((case or {}).get("ai_analysis_visible", True))


def queued_submission_limit(total_queued):
    return max(min(60 - int(total_queued), 15), 5)


def is_beijing_overnight_submission_window(now=None):
    current = now or datetime.now(timezone.utc)
    beijing_now = current.astimezone(BEIJING_TIMEZONE)
    return 0 <= beijing_now.hour < 7


def can_delete_submission_row(row, user):
    status = str(row.get("status") or "")
    if user["role"] == "admin":
        return status in ADMIN_DELETABLE_SUBMISSION_STATUSES
    return row.get("user_id") == user["id"] and status in CONTESTANT_DELETABLE_SUBMISSION_STATUSES


def delete_submission_denial_reason(row, user):
    status = str(row.get("status") or "")
    if user["role"] == "admin":
        if status not in ADMIN_DELETABLE_SUBMISSION_STATUSES:
            return "admin can only delete queued or completed submissions"
        return ""
    if row.get("user_id") != user["id"]:
        return "cannot delete other users' submissions"
    if status != "queued":
        return "contestants can only delete their own queued submissions"
    return ""


def can_retry_submission_row(row, user):
    status = str(row.get("status") or "")
    return user["role"] == "admin" and status in RETRYABLE_SUBMISSION_STATUSES


def retry_submission_denial_reason(row, user):
    if user["role"] != "admin":
        return "admin required"
    status = str(row.get("status") or "")
    if status not in RETRYABLE_SUBMISSION_STATUSES:
        return "admin can only retry completed or failed submissions"
    return ""


def validate_retry_skill_snapshot(skill_text, skills_json):
    raw_json = str(skills_json or "").strip()
    if not raw_json:
        return
    try:
        skills = normalize_stored_skill_entries(json.loads(raw_json))
    except Exception as exc:
        raise ValueError(f"submission skill snapshot is invalid: {exc}") from exc
    state_root = settings.STATE_DIR.resolve()
    for skill in skills:
        if skill.get("type") != SKILL_KIND_ARCHIVE:
            continue
        relpath = str(skill.get("storage_relpath") or "").replace("\\", "/").strip().strip("/")
        if not relpath:
            raise ValueError(f"archive skill '{skill['name']}' is missing, please re-upload it")
        target = (settings.STATE_DIR / relpath).resolve()
        try:
            target.relative_to(state_root)
        except ValueError as exc:
            raise ValueError(f"archive skill '{skill['name']}' has an invalid storage path") from exc
        if not target.exists():
            raise ValueError(f"archive skill '{skill['name']}' is missing, please re-upload it")


def submission_runtime_context(user, data):
    profile = get_user_profile(user["id"])
    model_profile = effective_model_profile(profile, include_secret=True)
    grader_profile = effective_grader_profile(profile, include_secret=True)
    if not model_profile["configured"]:
        raise ValueError("save Base URL, API key, and model before submitting")
    if not grader_profile["configured"]:
        raise ValueError("平台评分服务当前不可用，请联系管理员")
    selected_skills = selected_profile_skills(profile_skills(profile), data.get("skill_ids"))
    skill_fields = snapshot_submission_skills(selected_skills)
    soul_md = normalize_soul_markdown(profile.get("soul_md") or "")
    return {
        "model_profile": model_profile,
        "grader_profile": grader_profile,
        "skill_fields": skill_fields,
        "soul_md": soul_md,
    }


def enforce_queue_limit(conn, user, new_submission_count=1):
    if user["role"] == "admin":
        return
    own_queued = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM submissions
        WHERE status = 'queued' AND user_id = ?
        """,
        (user["id"],),
    ).fetchone()["n"]
    new_submission_count = max(1, int(new_submission_count or 1))
    if is_beijing_overnight_submission_window():
        if own_queued + new_submission_count > OVERNIGHT_QUEUE_LIMIT:
            raise ValueError(
                "overnight queue limit reached: this submission batch would exceed 50 queued submissions; "
                "contestant submissions reopen after 07:00 Beijing time"
            )
        return
    total_queued = conn.execute(
        "SELECT COUNT(*) AS n FROM submissions WHERE status = 'queued'"
    ).fetchone()["n"]
    limit = queued_submission_limit(total_queued)
    if own_queued + new_submission_count > limit:
        raise ValueError(
            f"queued submission limit reached: this submission batch would exceed your current limit "
            f"of {limit} queued submissions (currently {own_queued}, total queued: {total_queued})"
        )


def insert_submission_row(conn, user, data, runtime, now, extra=None):
    extra = extra or {}
    model_profile = runtime["model_profile"]
    grader_profile = runtime["grader_profile"]
    skill_fields = runtime["skill_fields"]
    cur = conn.execute(
        """
        INSERT INTO submissions (
            user_id, case_id, source_kind, test_set_id, test_set_name, test_set_case_index,
            display_case_name, submission_group_id, status, api_base_url, api_key, api_key_mask,
            grader_api_key, grader_api_key_mask, grader_base_url, grader_model, model, prompt,
            answer_mcp_servers_json, skill, skills_json, soul_md, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            data["case_id"],
            extra.get("source_kind", "case"),
            extra.get("test_set_id"),
            extra.get("test_set_name"),
            extra.get("test_set_case_index"),
            extra.get("display_case_name"),
            extra.get("submission_group_id"),
            model_profile["api_base_url"],
            model_profile["api_key"],
            model_profile["api_key_mask"] or mask_api_key(model_profile["api_key"]),
            grader_profile["api_key"],
            grader_profile["api_key_mask"] or mask_api_key(grader_profile["api_key"]),
            grader_profile["api_base_url"],
            grader_profile["model"],
            model_profile["model"],
            data["prompt"],
            dump_answer_mcp_servers_json(data.get("mcp_servers")),
            skill_fields["skill"],
            skill_fields["skills_json"],
            runtime["soul_md"],
            now,
            now,
        ),
    )
    return cur.lastrowid


def create_submission(user, data):
    now = utc_now()
    case = load_cases_map().get(data["case_id"])
    if not case:
        raise ValueError("unknown case")
    if user["role"] != "admin" and not is_training_case(case):
        raise ValueError("unknown case")
    if user["role"] != "admin" and not case_submission_enabled(case):
        raise ValueError("this case is currently unavailable for contestant submissions")
    runtime = submission_runtime_context(user, data)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        enforce_queue_limit(conn, user, 1)
        return insert_submission_row(conn, user, data, runtime, now)


def create_test_set_submissions(user, test_set_id, data):
    test_set = test_set_by_id(test_set_id)
    if not test_set:
        raise ValueError("test set not found")
    if user["role"] != "admin" and not test_set.get("submission_enabled", True):
        raise PermissionError("this test set is currently unavailable for contestant submissions")
    members = test_set_members(test_set["id"])
    if not members:
        raise ValueError("test set has no cases")
    runtime = submission_runtime_context(user, data)
    now = utc_now()
    group_id = uuid.uuid4().hex
    created_ids = []
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        enforce_queue_limit(conn, user, len(members))
        for index, case in enumerate(members, start=1):
            display_name = f"{test_set['name']}-{index}"
            created_ids.append(
                insert_submission_row(
                    conn,
                    user,
                    {
                        **data,
                        "case_id": case["id"],
                        "prompt": render_test_set_prompt(data["prompt"], case),
                    },
                    runtime,
                    now,
                    {
                        "source_kind": "test_set",
                        "test_set_id": test_set["id"],
                        "test_set_name": test_set["name"],
                        "test_set_case_index": index,
                        "display_case_name": display_name,
                        "submission_group_id": group_id,
                    },
                )
            )
    return {
        "created": len(created_ids),
        "submission_group_id": group_id,
    }


def retry_submission(submission_id, user):
    if user["role"] != "admin":
        raise PermissionError("admin required")
    cases = load_public_cases_map(include_test_cases=True, include_details=False)
    now = utc_now()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT s.*, u.username
            FROM submissions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (submission_id,),
        ).fetchone()
        if not row:
            raise LookupError("submission not found")
        item = dict(row)
        reason = retry_submission_denial_reason(item, user)
        if reason:
            raise ValueError(reason)
        case = cases.get(item["case_id"])
        if not case:
            raise ValueError("original case no longer exists")
        profile_row = conn.execute(
            """
            SELECT id, api_base_url, api_key, api_key_mask, model
            FROM users
            WHERE id = ?
            """,
            (item["user_id"],),
        ).fetchone()
        if not profile_row:
            raise ValueError("original user no longer exists")
        model_profile = effective_model_profile(dict(profile_row), include_secret=True)
        if not model_profile["configured"]:
            raise ValueError("original user has not saved a complete model configuration")
        grader_profile = effective_grader_profile({}, include_secret=True)
        if not grader_profile["configured"]:
            raise ValueError("platform scoring service is currently unavailable")
        validate_retry_skill_snapshot(item.get("skill") or "", item.get("skills_json") or "")
        cur = conn.execute(
            """
            INSERT INTO submissions (
                user_id, case_id, source_kind, test_set_id, test_set_name, test_set_case_index,
                display_case_name, submission_group_id, status, api_base_url, api_key, api_key_mask,
                grader_api_key, grader_api_key_mask, grader_base_url, grader_model, model, prompt,
                answer_mcp_servers_json, skill, skills_json, soul_md, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["user_id"],
                item["case_id"],
                item.get("source_kind") or "case",
                item.get("test_set_id"),
                item.get("test_set_name"),
                item.get("test_set_case_index"),
                item.get("display_case_name"),
                item.get("submission_group_id") or uuid.uuid4().hex if item.get("source_kind") == "test_set" else None,
                model_profile["api_base_url"],
                model_profile["api_key"],
                model_profile["api_key_mask"] or mask_api_key(model_profile["api_key"]),
                grader_profile["api_key"],
                grader_profile["api_key_mask"] or mask_api_key(grader_profile["api_key"]),
                grader_profile["api_base_url"],
                grader_profile["model"],
                model_profile["model"],
                item["prompt"],
                item.get(ANSWER_MCP_SNAPSHOT_COLUMN) or dump_answer_mcp_servers_json(default_case_mcp_servers()),
                item.get("skill") or "",
                item.get("skills_json") or "",
                item.get("soul_md") or "",
                now,
                now,
            ),
        )
        return cur.lastrowid


def is_test_set_submission(row, case=None):
    return str((row or {}).get("source_kind") or "case") == "test_set" or (
        case is not None and is_test_set_case(case)
    )


def is_hidden_submission(row, case=None):
    return case is not None and is_ungrouped_case(case) and not is_test_set_submission(row, case)


def submission_display_case_name(row, current_user, case=None):
    test_submission = is_test_set_submission(row, case)
    hidden_submission = is_hidden_submission(row, case)
    display_name = str((row or {}).get("display_case_name") or "").strip()
    if test_submission:
        return display_name or "测试集"
    if hidden_submission and current_user["role"] != "admin":
        return "未分组"
    case_name = str((row or {}).get("case_name") or "").strip()
    return case_name or str((row or {}).get("case_id") or "")


def submission_public(row, current_user, case=None):
    test_submission = is_test_set_submission(row, case)
    hidden_submission = is_hidden_submission(row, case)
    redact_hidden_submission = hidden_submission and current_user["role"] != "admin"
    can_view = current_user["role"] == "admin" or (
        row["user_id"] == current_user["id"] and not hidden_submission
    )
    can_delete = can_delete_submission_row(row, current_user)
    can_retry = can_retry_submission_row(row, current_user)
    can_view_ai_analysis = (
        current_user["role"] == "admin"
        or test_submission
        or case_ai_analysis_visible(case)
    )
    case_name = submission_display_case_name(row, current_user, case)
    public_case_id = row["case_id"] if not redact_hidden_submission else ""
    return {
        "id": row["id"],
        "username": row["username"],
        "case_id": public_case_id,
        "case_name": case_name,
        "source_kind": row.get("source_kind") or "case",
        "test_set_id": row.get("test_set_id") if test_submission else "",
        "test_set_name": row.get("test_set_name") if test_submission else "",
        "test_set_case_index": row.get("test_set_case_index") if test_submission else None,
        "display_case_name": row.get("display_case_name") or "",
        "status": row["status"],
        "api_base_url": row["api_base_url"] if can_view and not redact_hidden_submission else "",
        "model": row["model"],
        "score": row["score"],
        "verdict": verdict_for_score(row["score"]),
        "result_summary": row["result_summary"] if can_view and can_view_ai_analysis else "",
        "created_at": "" if redact_hidden_submission else row["created_at"],
        "started_at": "" if redact_hidden_submission else row["started_at"],
        "finished_at": "" if redact_hidden_submission else row["finished_at"],
        "updated_at": "" if redact_hidden_submission else row["updated_at"],
        "can_view_content": can_view,
        "can_delete": can_delete,
        "can_retry": can_retry,
    }


def public_test_set_display_names():
    names = set()
    for test_set in public_test_sets():
        name = str(test_set.get("name") or test_set.get("id") or "").strip()
        if not name:
            continue
        for index, _case_number in enumerate(test_set.get("case_numbers") or [], start=1):
            names.add(f"{name}-{index}")
    conn = db.connect()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT display_case_name
            FROM submissions
            WHERE source_kind = 'test_set'
              AND display_case_name IS NOT NULL
              AND display_case_name != ''
            """
        ).fetchall()
    finally:
        conn.close()
    names.update(str(row["display_case_name"]).strip() for row in rows if str(row["display_case_name"] or "").strip())
    return names


def public_test_set_filters(display_names=None):
    names = public_test_set_display_names() if display_names is None else display_names
    return [{"display_case_name": name} for name in sorted(names, key=lambda item: item.casefold())]


def normalize_submission_list_options(username="", case_id="", display_case_name="", sort_by="created_at", sort_order="desc", page=1, per_page=DEFAULT_SUBMISSIONS_PER_PAGE):
    username = str(username or "").strip()
    case_id = str(case_id or "").strip()
    display_case_name = str(display_case_name or "").strip()
    sort_by = "score" if str(sort_by or "").strip() == "score" else "created_at"
    sort_order = "asc" if str(sort_order or "").strip() == "asc" else "desc"
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(per_page)
    except (TypeError, ValueError):
        per_page = DEFAULT_SUBMISSIONS_PER_PAGE
    page = max(1, page)
    per_page = max(1, min(MAX_SUBMISSIONS_PER_PAGE, per_page))
    return {
        "username": username,
        "case_id": case_id,
        "display_case_name": display_case_name,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "page": page,
        "per_page": per_page,
    }


def submission_order_sql(sort_by, sort_order):
    if sort_by == "score":
        score_direction = "ASC" if sort_order == "asc" else "DESC"
        return (
            "ORDER BY CASE WHEN s.score IS NULL THEN 1 ELSE 0 END ASC, "
            f"s.score {score_direction}, s.created_at DESC, s.id DESC"
        )
    time_direction = "ASC" if sort_order == "asc" else "DESC"
    id_direction = "ASC" if sort_order == "asc" else "DESC"
    return f"ORDER BY s.created_at {time_direction}, s.id {id_direction}"


def list_submissions(user, username="", case_id="", display_case_name="", sort_by="created_at", sort_order="desc", page=1, per_page=DEFAULT_SUBMISSIONS_PER_PAGE):
    options = normalize_submission_list_options(username, case_id, display_case_name, sort_by, sort_order, page, per_page)
    test_set_display_names = public_test_set_display_names()
    test_set_filters = public_test_set_filters(test_set_display_names)
    cases = load_public_cases_map(include_test_cases=True, include_details=False)
    if options["case_id"] and user["role"] != "admin":
        requested_case = cases.get(options["case_id"])
        if not requested_case or is_ungrouped_case(requested_case):
            return {
                "submissions": [],
                "page": 1,
                "per_page": options["per_page"],
                "total": 0,
                "total_pages": 1,
                "test_set_filters": test_set_filters,
            }
    if options["display_case_name"] and user["role"] != "admin":
        if options["display_case_name"] not in test_set_display_names:
            return {
                "submissions": [],
                "page": 1,
                "per_page": options["per_page"],
                "total": 0,
                "total_pages": 1,
                "test_set_filters": test_set_filters,
            }
    where = []
    params = []
    if options["username"]:
        where.append("LOWER(u.username) LIKE ?")
        params.append(f"%{options['username'].lower()}%")
    if options["case_id"]:
        where.append("s.case_id = ?")
        params.append(options["case_id"])
    if options["display_case_name"]:
        where.append("s.source_kind = 'test_set'")
        where.append("s.display_case_name = ?")
        params.append(options["display_case_name"])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    order_sql = submission_order_sql(options["sort_by"], options["sort_order"])
    with db.connect() as conn:
        total = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM submissions s
            JOIN users u ON u.id = s.user_id
            {where_sql}
            """,
            params,
        ).fetchone()["n"]
        total_pages = max(1, (total + options["per_page"] - 1) // options["per_page"])
        page = min(options["page"], total_pages)
        offset = (page - 1) * options["per_page"]
        rows = conn.execute(
            f"""
            SELECT
                s.id,
                s.user_id,
                s.case_id,
                s.source_kind,
                s.test_set_id,
                s.test_set_name,
                s.test_set_case_index,
                s.display_case_name,
                s.status,
                s.api_base_url,
                s.model,
                s.score,
                s.result_summary,
                s.created_at,
                s.started_at,
                s.finished_at,
                s.updated_at,
                u.username
            FROM submissions s
            JOIN users u ON u.id = s.user_id
            {where_sql}
            {order_sql}
            LIMIT ? OFFSET ?
            """,
            params + [options["per_page"], offset],
        ).fetchall()
    payload = []
    for row in rows:
        item = dict(row)
        case = cases.get(row["case_id"], {})
        item["case_name"] = case.get("title", row["case_id"])
        payload.append(submission_public(item, user, case))
    return {
        "submissions": payload,
        "page": page,
        "per_page": options["per_page"],
        "total": total,
        "total_pages": total_pages,
        "test_set_filters": test_set_filters,
    }


def personal_best_scores_by_case(user_id):
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return {}
    if user_id <= 0:
        return {}
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT case_id, MAX(score) AS best_score
            FROM submissions
            WHERE user_id = ? AND score IS NOT NULL
            GROUP BY case_id
            """,
            (user_id,),
        ).fetchall()
    return {
        str(row["case_id"]): row["best_score"]
        for row in rows
        if row["case_id"] is not None
    }


def hidden_case_leaderboard(limit=DEFAULT_LEADERBOARD_LIMIT):
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_LEADERBOARD_LIMIT
    limit = max(1, min(500, limit))
    cases = load_cases_list()
    configured_test_set_ids = {
        str(item.get("id") or "").strip()
        for item in public_test_sets()
        if str(item.get("id") or "").strip()
    }
    test_set_case_ids = [
        case["id"]
        for case in cases
        if case_set_id(case) in configured_test_set_ids
    ]
    test_set_case_id_set = set(test_set_case_ids)
    hidden_case_ids = [
        case["id"]
        for case in cases
        if case["id"] not in test_set_case_id_set and not case_ai_analysis_visible(case)
    ]
    leaderboard_case_count = len(hidden_case_ids) + len(test_set_case_ids)
    if not leaderboard_case_count:
        return {
            "leaderboard": [],
            "hidden_case_count": 0,
            "test_set_case_count": 0,
            "leaderboard_case_count": 0,
        }

    score_conditions = []
    score_params = []
    if hidden_case_ids:
        placeholders = ", ".join("?" for _ in hidden_case_ids)
        score_conditions.append(f"s.case_id IN ({placeholders})")
        score_params.extend(hidden_case_ids)
    if test_set_case_ids:
        placeholders = ", ".join("?" for _ in test_set_case_ids)
        score_conditions.append(
            f"(s.case_id IN ({placeholders}) AND s.source_kind = 'test_set')"
        )
        score_params.extend(test_set_case_ids)
    score_filter = " OR ".join(f"({condition})" for condition in score_conditions)
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            WITH best_scores AS (
                SELECT
                    s.user_id,
                    s.case_id,
                    MAX(s.score) AS best_score,
                    MAX(COALESCE(s.finished_at, s.updated_at, s.created_at)) AS latest_score_at
                FROM submissions s
                JOIN users u ON u.id = s.user_id
                WHERE u.role = 'contestant'
                  AND u.disabled = 0
                  AND s.status = 'done'
                  AND s.score IS NOT NULL
                  AND ({score_filter})
                GROUP BY s.user_id, s.case_id
            )
            SELECT
                u.id AS user_id,
                u.username,
                COALESCE(SUM(best_scores.best_score), 0) AS total_score,
                COUNT(best_scores.case_id) AS scored_cases,
                MAX(best_scores.latest_score_at) AS latest_score_at
            FROM users u
            LEFT JOIN best_scores ON best_scores.user_id = u.id
            WHERE u.role = 'contestant'
              AND u.disabled = 0
            GROUP BY u.id, u.username
            HAVING COUNT(best_scores.case_id) > 0
            ORDER BY
                total_score DESC,
                scored_cases DESC,
                CASE WHEN latest_score_at IS NULL THEN 1 ELSE 0 END ASC,
                latest_score_at ASC,
                LOWER(u.username) ASC,
                u.id ASC
            LIMIT ?
            """,
            score_params + [limit],
        ).fetchall()
    leaderboard = []
    for index, row in enumerate(rows, start=1):
        leaderboard.append(
            {
                "rank": index,
                "user_id": row["user_id"],
                "username": row["username"],
                "total_score": int(row["total_score"] or 0),
                "scored_cases": int(row["scored_cases"] or 0),
                "latest_score_at": row["latest_score_at"] or "",
            }
        )
    return {
        "leaderboard": leaderboard,
        "hidden_case_count": leaderboard_case_count,
        "test_set_case_count": len(test_set_case_ids),
        "leaderboard_case_count": leaderboard_case_count,
    }


def queue_position(submission_id):
    with db.connect() as conn:
        row = conn.execute("SELECT status FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        if not row or row["status"] != "queued":
            return None
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM submissions WHERE status = 'queued' AND id < ?",
            (submission_id,),
        ).fetchone()["n"]
        return count + 1


def display_submission_error(item):
    error = item.get("error")
    if error == "answer agent failed; see transcript":
        return summarize_agent_failure(
            item.get("answer_returncode"),
            extract_process_stderr(item.get("answer_transcript") or ""),
        )
    if error == "grading agent failed; see transcript":
        return summarize_agent_failure(None, extract_process_stderr(item.get("grade_transcript") or ""))
    return error


def get_submission(submission_id, user):
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT s.*, u.username
            FROM submissions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (submission_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)

    case_summary = load_public_cases_map(include_test_cases=True, include_details=False).get(item["case_id"])
    if user["role"] != "admin":
        if item["user_id"] != user["id"]:
            return "forbidden"
        if is_hidden_submission(item, case_summary):
            return "forbidden"

    cases = load_cases_map()
    case = cases.get(item["case_id"])
    item["case"] = public_case(case) if case else None
    selected_mcp_servers = resolve_answer_mcp_servers(case=case, submission=item)
    item["answer_mcp_servers"] = selected_mcp_servers
    item["answer_mcp_server_labels"] = [
        {
            "id": server_name,
            "label": public_case_mcp_server_label(server_name),
        }
        for server_name in selected_mcp_servers
    ]
    item["queue_position"] = queue_position(submission_id)
    item["verdict"] = verdict_for_score(item.get("score"))
    item["can_delete"] = can_delete_submission_row(item, user)
    item["can_retry"] = can_retry_submission_row(item, user)
    item["can_view_ai_analysis"] = (
        user["role"] == "admin"
        or is_test_set_submission(item, case)
        or case_ai_analysis_visible(case)
    )
    item["error"] = display_submission_error(item)
    item["answer_process"] = answer_process_for_grading(item.get("answer_transcript") or "")
    item["grade_process"] = answer_process_for_grading(item.get("grade_transcript") or "")
    item["skill_names"] = [skill["name"] for skill in profile_skills(item)]
    if not item["can_view_ai_analysis"]:
        item["result_summary"] = ""
        item["grade_output"] = ""
        item["grade_json"] = None
        item["grade_process"] = ""
    item.pop("api_key", None)
    item.pop("grader_api_key", None)
    item.pop("answer_transcript", None)
    item.pop("grade_transcript", None)
    item.pop("skills_json", None)
    item.pop("runner_meta", None)
    item.pop(ANSWER_MCP_SNAPSHOT_COLUMN, None)
    return item


def update_submission(submission_id, **fields):
    if not fields:
        return
    fields["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [submission_id]
    with db.connect() as conn:
        conn.execute(f"UPDATE submissions SET {assignments} WHERE id = ?", values)


def append_submission_log(submission_id, message):
    with db.connect() as conn:
        row = conn.execute("SELECT run_log FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        if not row:
            return
        combined = truncate_text((row["run_log"] or "") + message)
        conn.execute(
            "UPDATE submissions SET run_log = ?, updated_at = ? WHERE id = ?",
            (combined, utc_now(), submission_id),
        )


def delete_submission(submission_id, user):
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT s.*, u.username
            FROM submissions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (submission_id,),
        ).fetchone()
        if not row:
            raise LookupError("submission not found")
        item = dict(row)
        reason = delete_submission_denial_reason(item, user)
        if reason:
            if user["role"] != "admin" and item.get("user_id") != user["id"]:
                raise PermissionError(reason)
            raise ValueError(reason)
        deleted = conn.execute(
            "DELETE FROM submissions WHERE id = ?",
            (submission_id,),
        ).rowcount or 0
        if deleted != 1:
            raise RuntimeError("failed to delete submission")
        cases = load_cases_map()
        case = cases.get(item["case_id"])
        return {
            "id": item["id"],
            "username": item["username"],
            "status": item["status"],
            "case_id": item["case_id"] if user["role"] == "admin" or not is_hidden_submission(item, case) else "",
        }


def claim_next_submission():
    conn = db.connect()
    try:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM submissions WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
        if not row:
            conn.execute("COMMIT")
            return None
        conn.execute(
            """
            UPDATE submissions
            SET status = 'running', started_at = ?, error = NULL, updated_at = ?
            WHERE id = ?
            """,
            (utc_now(), utc_now(), row["id"]),
        )
        conn.execute("COMMIT")
        item = dict(row)
        item["status"] = "running"
        return item
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def reset_interrupted_submissions():
    placeholders = ",".join("?" for _ in INTERRUPTED_STATUSES)
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT id, status FROM submissions WHERE status IN ({placeholders})",
            INTERRUPTED_STATUSES,
        ).fetchall()
        for row in rows:
            message = f"\n[{utc_now()}] server restarted while submission was {row['status']}; re-queued.\n"
            conn.execute(
                """
                UPDATE submissions
                SET status = 'queued',
                    error = NULL,
                    run_log = COALESCE(run_log, '') || ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (message, utc_now(), row["id"]),
            )


def wait_stream_items(submission_id, user, deadline_seconds):
    last_seen = None
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        item = get_submission(submission_id, user)
        if item in (None, "forbidden"):
            return
        marker = (
            item.get("status"),
            len(item.get("run_log") or ""),
            item.get("updated_at"),
            item.get("answer_output"),
            item.get("grade_output"),
            item.get("grade_json"),
        )
        if marker != last_seen:
            last_seen = marker
            yield item
        if item.get("status") in {"done", "failed"}:
            return
        time.sleep(0.25)
