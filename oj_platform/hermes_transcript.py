import json
import re
import sqlite3

from .textutil import truncate_text
from .timeutil import utc_now


def parse_json_maybe(value):
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


def compact_tool_argument(value, limit=900):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[:limit] + f"\n[truncated {len(value) - limit} chars]"


def format_tool_call_summary(tool_calls):
    calls = parse_json_maybe(tool_calls)
    if not calls:
        return ""
    if isinstance(calls, dict):
        calls = [calls]
    lines = []
    for index, call in enumerate(calls, start=1):
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = call.get("name") or function.get("name") or call.get("tool_name") or "tool"
        raw_args = call.get("arguments")
        if raw_args is None:
            raw_args = function.get("arguments")
        args = parse_json_maybe(raw_args)
        if isinstance(args, dict):
            command = args.get("command") or args.get("cmd") or args.get("code") or args.get("query") or args.get("input")
            lines.append(f"{index}. {name}: {compact_tool_argument(command or args)}")
        else:
            lines.append(f"{index}. {name}: {compact_tool_argument(raw_args)}")
    return "Tool calls:\n" + "\n".join(lines) if lines else ""


def read_hermes_conversation(home):
    db_path = home / "state.db"
    if not db_path.exists():
        return "", ""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT role, content, tool_name, tool_calls, finish_reason, timestamp
            FROM messages
            ORDER BY id
            """
        ).fetchall()
    except Exception:
        return "", ""
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
    lines = []
    final_assistant = ""
    for row in rows:
        role = row["role"] or "message"
        content = row["content"] or ""
        tool_summary = format_tool_call_summary(row["tool_calls"])
        if tool_summary:
            content = f"{content}\n\n{tool_summary}".strip()
        title = role
        if row["tool_name"]:
            title += f" / {row['tool_name']}"
        if row["finish_reason"]:
            title += f" ({row['finish_reason']})"
        lines.append(f"### {title}\n{content}".strip())
        if role == "assistant" and content.strip():
            final_assistant = content.strip()
    return "\n\n".join(lines), final_assistant


def read_hermes_messages_since(home, last_id):
    db_path = home / "state.db"
    if not db_path.exists():
        return []
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=1)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, role, content, tool_name, tool_calls, finish_reason, timestamp
            FROM messages
            WHERE id > ?
            ORDER BY id
            """,
            (last_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def compact_live_text(text, limit=600):
    text = (text or "").strip()
    lines = [line.strip() for line in text.replace("\r", "").splitlines() if line.strip()]
    text = " / ".join(lines)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"...[truncated {len(text) - limit} chars; full content is in transcript]"


def format_hermes_live_message(row, live_prefix):
    role = row.get("role") or "message"
    content = (row.get("content") or "").strip()
    tool_summary = format_tool_call_summary(row.get("tool_calls"))
    if role in {"user", "system"}:
        return ""
    if role == "assistant" and content.lstrip().startswith("### tool"):
        return ""
    if role == "tool":
        return ""
    if role != "assistant" or not (row.get("finish_reason") == "tool_calls" or tool_summary):
        return ""
    label = "stage"
    body = compact_live_text(content)
    if not body:
        return ""
    prefix = f"[{utc_now()}] {live_prefix}/{label}: "
    return prefix + body + "\n"


def answer_process_for_grading(transcript):
    if not transcript:
        return ""
    marker = "--- hermes conversation ---"
    conversation = transcript.split(marker, 1)[1] if marker in transcript else transcript
    blocks = []
    for match in re.finditer(r"### ([^\n]+)\n(.*?)(?=\n\n### |\Z)", conversation, flags=re.DOTALL):
        title = match.group(1).strip()
        role = title.split("/", 1)[0].split("(", 1)[0].strip().lower()
        if role in {"user", "system"}:
            continue
        content = match.group(2).strip()
        if content:
            blocks.append(f"### {title}\n{content}")
    return truncate_text("\n\n".join(blocks))


def answer_process_for_api_grading(transcript, final_output="", block_limit=1800):
    """Keep diagnostic process blocks, excluding the separately supplied final answer."""
    if not transcript:
        return ""
    normalized_final = (final_output or "").strip()
    marker = "--- hermes conversation ---"
    conversation = transcript.split(marker, 1)[1] if marker in transcript else transcript
    blocks = []
    for match in re.finditer(r"### ([^\n]+)\n(.*?)(?=\n\n### |\Z)", conversation, flags=re.DOTALL):
        title = match.group(1).strip()
        role = title.split("/", 1)[0].split("(", 1)[0].strip().lower()
        if role in {"user", "system"}:
            continue
        content = match.group(2).strip()
        if not content:
            continue
        if normalized_final and role == "assistant" and content == normalized_final:
            continue
        if len(content) > block_limit:
            omitted = len(content) - block_limit
            content = content[:block_limit] + f"\n...[truncated {omitted} chars]"
        blocks.append(f"### {title}\n{content}")
    return "\n\n".join(blocks)


def extract_process_stderr(transcript):
    if not transcript:
        return ""
    match = re.search(
        r"--- stderr ---\n(.*?)(?:\n\n--- hermes conversation ---|$)",
        transcript,
        flags=re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def summarize_agent_failure(returncode, stderr):
    text = stderr or ""
    lower = text.lower()
    if "403" in lower or "forbidden" in lower or "request was blocked" in lower:
        return "model request was rejected; check Base URL, API key, and model name"
    if returncode == 124 or "timed out after" in lower or "timeout" in lower:
        return "agent timed out; check model latency or reduce tool/prompt cost"
    if "unknown toolsets" in lower:
        return "Hermes toolset config is invalid; check OJ_HERMES_TOOLSETS"
    if returncode is not None:
        return f"agent failed with returncode={returncode}; see process log"
    return "agent failed; see process log"
