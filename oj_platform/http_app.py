import json
import mimetypes
import re
import sqlite3
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlparse

from . import db, settings
from .cases import (
    admin_case_files,
    admin_public_content,
    create_case_files,
    create_case_files_from_archive,
    create_next_test_set,
    delete_case_files,
    delete_test_set,
    is_ungrouped_case,
    load_public_cases_list,
    load_public_cases_map,
    public_case,
    public_config,
    public_test_sets,
    update_case_flags,
    update_case_files,
    update_public_content,
    update_test_set,
    update_test_set_flags,
)
from .hermes_runner import agent_status
from .model_config import (
    check_grader_profile_available,
    check_model_available,
    model_check_fields,
    public_grader_config,
    update_user_grader_config,
    update_user_profile,
)
from .security import make_token, verify_password, verify_token
from .submissions import (
    create_submission,
    create_test_set_submissions,
    delete_submission,
    get_submission,
    hidden_case_leaderboard,
    list_submissions,
    personal_best_scores_by_case,
    queue_position,
    retry_submission,
    validate_submission_payload,
    validate_test_set_submission_payload,
    wait_stream_items,
)
from .timeutil import utc_now
from .users import (
    create_user,
    get_user_by_id,
    get_user_profile,
    list_admin_users,
    public_admin_user,
    public_session_user,
    public_user_profile,
    delete_admin_user,
    update_admin_user,
    update_user_skill_profile,
    update_user_soul_profile,
    upload_user_archive_skill,
)


def json_response(handler, payload, status=HTTPStatus.OK):
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_request_json(handler):
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length > 2_000_000:
        raise ValueError("request body too large")
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def get_authenticated_user(handler):
    auth = handler.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = verify_token(auth.split(" ", 1)[1].strip())
    if not payload:
        return None
    return get_user_by_id(payload.get("sub"))


def require_user(handler):
    user = get_authenticated_user(handler)
    if not user:
        json_response(handler, {"error": "authentication required"}, HTTPStatus.UNAUTHORIZED)
        return None
    return user


def require_admin(handler):
    user = require_user(handler)
    if not user:
        return None
    if user["role"] != "admin":
        json_response(handler, {"error": "admin required"}, HTTPStatus.FORBIDDEN)
        return None
    return user


def public_cases_for_user(user):
    best_scores = personal_best_scores_by_case(user["id"])
    payload = []
    for item in load_public_cases_list(include_test_cases=True):
        if user["role"] != "admin" and is_ungrouped_case(item):
            continue
        item = dict(item)
        if item.get("id") in best_scores:
            item["personal_best_score"] = best_scores[item["id"]]
        payload.append(item)
    return payload


def stream_submission_detail(handler, submission_id, user):
    item = get_submission(submission_id, user)
    if item == "forbidden":
        json_response(handler, {"error": "forbidden"}, HTTPStatus.FORBIDDEN)
        return
    if not item:
        json_response(handler, {"error": "submission not found"}, HTTPStatus.NOT_FOUND)
        return

    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.end_headers()

    deadline = (
        settings.AGENT_TIMEOUT_SECONDS
        + settings.JUDGE_TIMEOUT_SECONDS
        + settings.FAULT_SCRIPT_TIMEOUT_SECONDS
        + 120
    )
    try:
        for item in wait_stream_items(submission_id, user, deadline):
            body = json.dumps({"submission": item}, ensure_ascii=False).encode("utf-8") + b"\n"
            handler.wfile.write(body)
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        return


class Handler(SimpleHTTPRequestHandler):
    server_version = "AIOpsOJ/2.0"

    def log_message(self, fmt, *args):
        print(f"[{utc_now()}] {self.address_string()} {fmt % args}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/health":
            json_response(self, {"ok": True, "time": utc_now(), "agent": agent_status()})
            return
        if path == "/api/me":
            user = require_user(self)
            if user:
                user = dict(user)
                user["profile_configured"] = public_user_profile(get_user_profile(user["id"]))["configured"]
                json_response(self, {"user": user})
            return
        if path == "/api/profile":
            user = require_user(self)
            if user:
                json_response(self, {"profile": public_user_profile(get_user_profile(user["id"]))})
            return
        if path == "/api/bootstrap":
            user = require_user(self)
            if user:
                profile = public_user_profile(get_user_profile(user["id"]))
                session_user = dict(user)
                session_user["profile_configured"] = profile["configured"]
                json_response(
                    self,
                    {
                        "user": session_user,
                        "profile": profile,
                        "config": public_config(),
                        "cases": public_cases_for_user(user),
                    },
                )
            return
        if path == "/api/config":
            if require_user(self):
                json_response(self, public_config())
            return
        if path == "/api/cases":
            user = require_user(self)
            if user:
                json_response(self, {"cases": public_cases_for_user(user)})
            return
        if path == "/api/test-sets":
            if require_user(self):
                json_response(self, {"test_sets": public_test_sets()})
            return
        if path == "/api/leaderboard":
            user = require_user(self)
            if user:
                query = parse_qs(parsed.query)
                json_response(
                    self,
                    hidden_case_leaderboard(query.get("limit", ["100"])[0]),
                )
            return
        if path.startswith("/api/cases/"):
            user = require_user(self)
            if not user:
                return
            case_id = path.rsplit("/", 1)[-1]
            case = load_public_cases_map(include_test_cases=True).get(case_id)
            if case and user["role"] != "admin" and is_ungrouped_case(case):
                case = None
            if not case:
                json_response(self, {"error": "case not found"}, HTTPStatus.NOT_FOUND)
                return
            json_response(self, dict(case))
            return
        if path == "/api/submissions":
            user = require_user(self)
            if user:
                query = parse_qs(parsed.query)
                json_response(
                    self,
                    list_submissions(
                        user,
                        username=query.get("username", [""])[0],
                        case_id=query.get("case_id", [""])[0],
                        display_case_name=query.get("display_case_name", [""])[0],
                        sort_by=query.get("sort_by", ["created_at"])[0],
                        sort_order=query.get("sort_order", ["desc"])[0],
                        page=query.get("page", ["1"])[0],
                        per_page=query.get("per_page", ["20"])[0],
                    ),
                )
            return
        stream_match = re.fullmatch(r"/api/submissions/(\d+)/stream", path)
        if stream_match:
            user = require_user(self)
            if user:
                stream_submission_detail(self, int(stream_match.group(1)), user)
            return
        if path.startswith("/api/submissions/"):
            user = require_user(self)
            if not user:
                return
            try:
                submission_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                json_response(self, {"error": "invalid submission id"}, HTTPStatus.BAD_REQUEST)
                return
            item = get_submission(submission_id, user)
            if item == "forbidden":
                json_response(self, {"error": "forbidden"}, HTTPStatus.FORBIDDEN)
            elif not item:
                json_response(self, {"error": "submission not found"}, HTTPStatus.NOT_FOUND)
            else:
                json_response(self, {"submission": item})
            return
        if path == "/api/admin/users":
            if require_admin(self):
                json_response(self, {"users": [public_admin_user(row) for row in list_admin_users()]})
            return
        if path == "/api/admin/public-content":
            if require_admin(self):
                json_response(self, admin_public_content())
            return
        if path == "/api/admin/test-sets":
            if require_admin(self):
                json_response(self, {"test_sets": public_test_sets()})
            return
        admin_case_match = re.fullmatch(r"/api/admin/cases/([^/]+)", path)
        if admin_case_match:
            user = require_admin(self)
            if user:
                try:
                    json_response(self, admin_case_files(admin_case_match.group(1)))
                except Exception as exc:
                    json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/admin/agent-status":
            user = require_admin(self)
            if user:
                json_response(self, {**agent_status(), "grader": public_grader_config(get_user_profile(user["id"]))})
            return
        if path == "/api/admin/grader-config":
            user = require_admin(self)
            if user:
                json_response(self, {"grader": public_grader_config(get_user_profile(user["id"]))})
            return
        self.serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/admin/cases/import-zip":
            user = require_admin(self)
            if not user:
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                length = 0
            if length <= 0:
                json_response(self, {"error": "request body is empty"}, HTTPStatus.BAD_REQUEST)
                return
            if length > settings.MAX_CASE_ARCHIVE_BYTES:
                json_response(
                    self,
                    {"error": f"zip archive is too large, max {settings.MAX_CASE_ARCHIVE_BYTES} bytes"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            filename = unquote(self.headers.get("X-Case-Archive-Name", "")).strip() or "case.zip"
            try:
                archive_bytes = self.rfile.read(length)
                result = create_case_files_from_archive(filename, archive_bytes)
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, result, HTTPStatus.CREATED)
            return
        if path == "/api/profile/skills/upload":
            user = require_user(self)
            if not user:
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                length = 0
            if length <= 0:
                json_response(self, {"error": "request body is empty"}, HTTPStatus.BAD_REQUEST)
                return
            if length > settings.MAX_SKILL_ARCHIVE_BYTES:
                json_response(
                    self,
                    {"error": f"zip archive is too large, max {settings.MAX_SKILL_ARCHIVE_BYTES} bytes"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            filename = unquote(self.headers.get("X-Skill-File-Name", "")).strip()
            try:
                archive_bytes = self.rfile.read(length)
                profile = upload_user_archive_skill(user["id"], filename, archive_bytes)
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"profile": public_user_profile(profile)}, HTTPStatus.CREATED)
            return
        admin_retry_match = re.fullmatch(r"/api/admin/submissions/(\d+)/retry", path)
        if admin_retry_match:
            user = require_admin(self)
            if not user:
                return
            try:
                new_submission_id = retry_submission(int(admin_retry_match.group(1)), user)
            except LookupError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            except PermissionError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.FORBIDDEN)
                return
            except ValueError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(
                self,
                {"id": new_submission_id, "queue_position": queue_position(new_submission_id)},
                HTTPStatus.CREATED,
            )
            return
        try:
            payload = read_request_json(self)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/auth/login":
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))
            with db.connect() as conn:
                row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row or row["disabled"] or not verify_password(password, row["password_hash"]):
                json_response(self, {"error": "invalid username or password"}, HTTPStatus.UNAUTHORIZED)
                return
            user = public_session_user(row)
            json_response(self, {"token": make_token(user), "user": user})
            return

        if path == "/api/auth/register":
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))
            invite_code = str(payload.get("invite_code", "")).strip()
            if invite_code != settings.REGISTRATION_INVITE_CODE:
                json_response(self, {"error": "invalid invite code"}, HTTPStatus.FORBIDDEN)
                return
            try:
                user_id = create_user(username, password, "contestant")
                with db.connect() as conn:
                    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            except sqlite3.IntegrityError:
                json_response(self, {"error": "username already exists"}, HTTPStatus.CONFLICT)
                return
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            user = public_session_user(row)
            json_response(self, {"token": make_token(user), "user": user}, HTTPStatus.CREATED)
            return

        if path == "/api/submissions":
            user = require_user(self)
            if not user:
                return
            try:
                data = validate_submission_payload(payload)
                submission_id = create_submission(user, data)
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"id": submission_id, "queue_position": queue_position(submission_id)}, HTTPStatus.CREATED)
            return

        test_set_submit_match = re.fullmatch(r"/api/test-sets/([^/]+)/submissions", path)
        if test_set_submit_match:
            user = require_user(self)
            if not user:
                return
            try:
                data = validate_test_set_submission_payload(payload)
                result = create_test_set_submissions(user, test_set_submit_match.group(1), data)
            except PermissionError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.FORBIDDEN)
                return
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, result, HTTPStatus.CREATED)
            return

        if path == "/api/profile/check":
            user = require_user(self)
            if not user:
                return
            try:
                base_url, api_key, model = model_check_fields(payload, get_user_profile(user["id"]))
                result = check_model_available(base_url, api_key, model)
            except Exception as exc:
                result = {"ok": False, "message": str(exc)}
            json_response(self, result)
            return

        if path == "/api/profile/grader/check":
            user = require_user(self)
            if not user:
                return
            try:
                result = check_grader_profile_available(payload, get_user_profile(user["id"]))
            except Exception as exc:
                result = {"ok": False, "message": str(exc)}
            if result.get("ok"):
                result["message"] = "scoring API is managed by the platform; current platform configuration is available"
            else:
                result["message"] = (
                    result.get("message")
                    or "scoring API is managed by the platform and is currently unavailable"
                )
            result["managed"] = True
            json_response(self, result)
            return

        if path == "/api/profile":
            user = require_user(self)
            if not user:
                return
            try:
                profile = update_user_profile(user, payload)
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"profile": public_user_profile(profile)})
            return

        if path == "/api/profile/skills":
            user = require_user(self)
            if not user:
                return
            try:
                profile = update_user_skill_profile(user["id"], payload.get("skills"))
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"profile": public_user_profile(profile)})
            return

        if path == "/api/admin/users":
            if not require_admin(self):
                return
            try:
                create_user(
                    str(payload.get("username", "")).strip(),
                    str(payload.get("password", "")),
                    str(payload.get("role", "contestant")).strip(),
                )
            except sqlite3.IntegrityError:
                json_response(self, {"error": "username already exists"}, HTTPStatus.CONFLICT)
                return
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"ok": True}, HTTPStatus.CREATED)
            return

        if path == "/api/admin/cases":
            if not require_admin(self):
                return
            try:
                json_response(self, create_case_files(payload), HTTPStatus.CREATED)
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/admin/test-sets":
            if not require_admin(self):
                return
            try:
                test_set = create_next_test_set()
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"test_set": test_set, "test_sets": public_test_sets()}, HTTPStatus.CREATED)
            return

        if path == "/api/admin/grader-config/check":
            json_response(self, {"ok": False, "message": "grader config moved to personal profile"}, HTTPStatus.GONE)
            return

        json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            payload = read_request_json(self)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/profile":
            user = require_user(self)
            if not user:
                return
            try:
                profile = update_user_profile(user, payload)
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"profile": public_user_profile(profile)})
            return

        if path == "/api/profile/grader":
            user = require_user(self)
            if not user:
                return
            json_response(
                self,
                {
                    "ok": False,
                    "managed": True,
                    "message": "scoring API is managed by the platform and cannot be edited",
                },
                HTTPStatus.CONFLICT,
            )
            return

        if path == "/api/profile/skills":
            user = require_user(self)
            if not user:
                return
            try:
                profile = update_user_skill_profile(user["id"], payload.get("skills"))
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"profile": public_user_profile(profile)})
            return

        if path == "/api/profile/soul":
            user = require_user(self)
            if not user:
                return
            try:
                profile = update_user_soul_profile(user["id"], payload.get("soul_md"))
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"profile": public_user_profile(profile)})
            return

        if path == "/api/admin/grader-config":
            json_response(self, {"error": "grader config moved to personal profile"}, HTTPStatus.GONE)
            return

        if not require_admin(self):
            return
        if path == "/api/admin/public-content":
            try:
                json_response(self, update_public_content(payload))
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        admin_case_flags_match = re.fullmatch(r"/api/admin/cases/([^/]+)/flags", path)
        if admin_case_flags_match:
            try:
                json_response(self, update_case_flags(admin_case_flags_match.group(1), payload))
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        admin_test_set_flags_match = re.fullmatch(r"/api/admin/test-sets/([^/]+)/flags", path)
        if admin_test_set_flags_match:
            try:
                json_response(self, update_test_set_flags(admin_test_set_flags_match.group(1), payload))
            except LookupError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.NOT_FOUND)
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        admin_test_set_match = re.fullmatch(r"/api/admin/test-sets/([^/]+)", path)
        if admin_test_set_match:
            try:
                json_response(self, update_test_set(admin_test_set_match.group(1), payload))
            except LookupError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.NOT_FOUND)
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        admin_case_match = re.fullmatch(r"/api/admin/cases/([^/]+)", path)
        if admin_case_match:
            try:
                json_response(self, update_case_files(admin_case_match.group(1), payload))
            except Exception as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path.startswith("/api/admin/users/"):
            try:
                user_id = int(path.rsplit("/", 1)[-1])
                row = update_admin_user(user_id, payload)
            except ValueError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"ok": True, "user": public_admin_user(row) if row else None})
            return
        json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        submission_match = re.fullmatch(r"/api/submissions/(\d+)", path)
        if submission_match:
            user = require_user(self)
            if not user:
                return
            try:
                deleted = delete_submission(int(submission_match.group(1)), user)
            except LookupError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            except PermissionError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.FORBIDDEN)
                return
            except ValueError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"ok": True, "deleted": deleted})
            return

        admin_user_match = re.fullmatch(r"/api/admin/users/(\d+)", path)
        if admin_user_match:
            if not require_admin(self):
                return
            try:
                deleted = delete_admin_user(int(admin_user_match.group(1)))
            except LookupError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            except ValueError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"ok": True, "deleted": deleted})
            return

        admin_case_match = re.fullmatch(r"/api/admin/cases/([^/]+)", path)
        if admin_case_match:
            if not require_admin(self):
                return
            try:
                deleted = delete_case_files(admin_case_match.group(1))
            except LookupError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            except ValueError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"ok": True, "deleted": deleted})
            return

        admin_test_set_match = re.fullmatch(r"/api/admin/test-sets/([^/]+)", path)
        if admin_test_set_match:
            if not require_admin(self):
                return
            try:
                result = delete_test_set(admin_test_set_match.group(1))
            except LookupError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            except ValueError as exc:
                json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, result)
            return

        json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

    def serve_static(self, path):
        if path == "/":
            target = settings.STATIC_DIR / "index.html"
        elif path.startswith("/static/"):
            target = (settings.ROOT / path.lstrip("/")).resolve()
        else:
            target = settings.STATIC_DIR / "index.html"
        try:
            target.relative_to(settings.ROOT)
        except ValueError:
            json_response(self, {"error": "invalid path"}, HTTPStatus.BAD_REQUEST)
            return
        if not target.exists() or not target.is_file():
            json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "text/plain"
        if content_type.startswith("text/") or target.suffix in {".js", ".css"}:
            content_type += "; charset=utf-8"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
