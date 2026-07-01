import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import settings
from .grading import extract_json_object
from .submissions import append_submission_log, update_submission
from .timeutil import utc_now


def _error_detail(exc):
    try:
        detail = exc.read(2000).decode("utf-8", errors="replace").strip()
    except Exception:
        detail = ""
    return detail or str(getattr(exc, "reason", exc))


def _build_display(reasoning_parts, content):
    reasoning = "".join(reasoning_parts).strip()
    content = (content or "").strip()
    thinking_label = "[\u601d\u8003\u8fc7\u7a0b]"
    json_label = "[\u6700\u7ec8\u8bc4\u5206 JSON]"
    if reasoning and content:
        return f"{thinking_label}\n{reasoning}\n\n{json_label}\n{content}"
    if reasoning:
        return f"{thinking_label}\n{reasoning}"
    return content


def stream_grading_completion(submission_id, messages, grader, timeout=None):
    timeout = timeout or settings.JUDGE_TIMEOUT_SECONDS
    model = str(grader.get("model") or settings.GRADER_MODEL).strip() or settings.GRADER_MODEL
    base_url = str(grader.get("api_base_url") or settings.GRADER_BASE_URL).strip().rstrip("/") or settings.GRADER_BASE_URL
    api_key = str(grader.get("api_key") or "").strip()
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled"},
        "stream": True,
        "max_tokens": 16384,
    }
    request = Request(
        base_url + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": settings.MODEL_CHECK_USER_AGENT,
        },
        method="POST",
    )
    transcript = json.dumps(
        {
            "provider": base_url,
            "model": model,
            "thinking": "enabled",
            "json_mode": True,
            "stream": True,
        },
        ensure_ascii=False,
    )
    append_submission_log(
        submission_id,
        f"[{utc_now()}] grade-api: requesting {model} from {base_url} with thinking and JSON streaming enabled\n",
    )
    update_submission(submission_id, grade_output="")
    reasoning_parts = []
    parts = []
    thinking_seen = False
    last_publish = 0.0
    try:
        with urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                if not data:
                    continue
                event = json.loads(data)
                choices = event.get("choices") or []
                delta = choices[0].get("delta") if choices else {}
                delta = delta if isinstance(delta, dict) else {}
                reasoning = delta.get("reasoning_content") or ""
                if reasoning and not thinking_seen:
                    append_submission_log(submission_id, f"[{utc_now()}] grade-api: thinking stream started\n")
                    thinking_seen = True
                if reasoning:
                    reasoning_parts.append(reasoning)
                content = delta.get("content") or ""
                if content and not parts:
                    append_submission_log(submission_id, f"[{utc_now()}] grade-api: JSON stream started\n")
                if content:
                    parts.append(content)
                if not reasoning and not content:
                    continue
                now = time.monotonic()
                if now - last_publish >= 0.15:
                    partial_output = "".join(parts)
                    update_submission(submission_id, grade_output=_build_display(reasoning_parts, partial_output))
                    last_publish = now
        output = "".join(parts).strip()
        if not output and reasoning_parts:
            fallback = "".join(reasoning_parts).strip()
            parsed = extract_json_object(fallback)
            if parsed:
                output = json.dumps(parsed, ensure_ascii=False)
                append_submission_log(submission_id, f"[{utc_now()}] grade-api: recovered JSON from reasoning stream\n")
        display = _build_display(reasoning_parts, output)
        update_submission(submission_id, grade_output=display)
        if not output.strip():
            return {
                "ok": False,
                "stdout": output,
                "display": display,
                "transcript": transcript,
                "error": "scoring API returned empty JSON content",
            }
        append_submission_log(submission_id, f"[{utc_now()}] grade-api: JSON response complete\n")
        return {"ok": True, "stdout": output, "display": display, "transcript": transcript, "error": None}
    except HTTPError as exc:
        output = "".join(parts)
        error = f"scoring API failed: HTTP {exc.code} {_error_detail(exc)}"
    except URLError as exc:
        output = "".join(parts)
        error = f"scoring API failed: {exc.reason}"
    except Exception as exc:
        output = "".join(parts)
        error = f"scoring API failed: {exc}"
    display = _build_display(reasoning_parts, output)
    update_submission(submission_id, grade_output=display)
    append_submission_log(submission_id, f"[{utc_now()}] grade-api: {error}\n")
    return {"ok": False, "stdout": output, "display": display, "transcript": transcript, "error": error}
