import json
import os
import shutil
from pathlib import Path

from . import settings
from .mcp import (
    ALIBABA_MCP_SERVER_NAME,
    MULTI_CLOUD_SSH_MCP_SERVER_NAME,
    RUM_MCP_SERVER_NAME,
    RUM2_MCP_SERVER_NAME,
    selected_mcp_config,
)
from .skills import write_contestant_skills
from .soul import write_soul_markdown


RUNNER_SCRIPT = """#!/usr/bin/env python3
import atexit
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

hermes_lib, prompt_path, provider, model, toolsets, skills, max_turns = sys.argv[1:8]
sys.path.insert(0, hermes_lib)
if os.environ.get("OJ_HERMES_UNATTENDED") == "1":
    os.environ.setdefault("HERMES_YOLO_MODE", "1")
    os.environ.setdefault("HERMES_ACCEPT_HOOKS", "1")

from cli import (
    HermesCLI,
    _parse_skills_argument,
    _run_cleanup,
)

OJ_EVENT_PREFIX = "__OJ_EVENT__ "
_print_lock = threading.Lock()


def _redact(text):
    text = str(text or "")
    text = re.sub(r"(?i)(api[_-]?key|password|passwd|secret|token)(['\\\"]?\\s*[:=]\\s*['\\\"]?)[^\\s,'\\\"]+", r"\\1\\2***", text)
    text = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-***", text)
    return text


def _compact(value, limit=1200):
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except Exception:
            value = str(value)
    value = _redact(value.replace("\\r", "").strip())
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    value = "\\n".join(lines)
    if len(value) > limit:
        value = value[:limit].rstrip() + "...[truncated]"
    return value


def _preview_args(tool_name, args):
    args = args or {}
    if isinstance(args, dict):
        for key in ("cmd", "command", "script", "query", "path"):
            if args.get(key):
                return _compact(args.get(key), 180)
    return _compact(args, 180)


def _summarize_result(result):
    raw = _compact(result, 900)
    try:
        parsed = json.loads(result) if isinstance(result, str) else result
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        parts = []
        for key in ("exit_code", "returncode", "status", "error"):
            if key in parsed and parsed.get(key) not in (None, ""):
                parts.append(f"{key}={_compact(parsed.get(key), 160)}")
        for key in ("stderr", "stdout", "output", "summary"):
            if key in parsed and parsed.get(key):
                parts.append(f"{key}: {_compact(parsed.get(key), 180)}")
        if parts:
            return _compact("; ".join(parts), 240)
    return _compact(raw, 240)


def _emit(event, **payload):
    payload["event"] = event
    line = OJ_EVENT_PREFIX + json.dumps(payload, ensure_ascii=False, default=str)
    with _print_lock:
        print(line, flush=True)


def _toolsets_list(raw):
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _install_live_callbacks(agent):
    starts = {}
    stage_parts = []

    def flush_stage():
        text = _compact("".join(stage_parts), 600)
        stage_parts.clear()
        if text:
            _emit("stage.message", summary=text)

    def on_delta(delta):
        if delta is None:
            flush_stage()
            return
        if not isinstance(delta, str) or not delta:
            return
        stage_parts.append(delta)
        buffered = "".join(stage_parts)
        if len(buffered) > 3000:
            stage_parts[:] = [buffered[-3000:]]

    def on_start(tool_call_id, name, args):
        flush_stage()
        starts[tool_call_id] = time.time()
        _emit("tool.started", tool=name, preview=_preview_args(name, args))

    def on_complete(tool_call_id, name, args, result):
        duration = None
        started_at = starts.pop(tool_call_id, None)
        if started_at is not None:
            duration = round(time.time() - started_at, 2)
        summary = _summarize_result(result)
        _emit("tool.completed", tool=name, duration=duration, summary=summary)

    agent.tool_start_callback = on_start
    agent.tool_complete_callback = on_complete
    agent.stream_delta_callback = on_delta


def _discover_mcp_toolsets(toolsets):
    active_servers = [
        server
        for server in ("alibaba-cloud-ops-mcp-server", "k3s-cluster", "rum", "rum2", "multi-cloud-ssh")
        if server in toolsets
    ]
    if not active_servers:
        return
    try:
        from tools.mcp_tool import discover_mcp_tools

        tools = discover_mcp_tools()
    except Exception as exc:
        _emit("mcp.error", message=_compact(str(exc), 360))
        return
    if tools:
        _emit("mcp.ready", server=",".join(active_servers), tool_count=len(tools))
    else:
        _emit("mcp.error", server=",".join(active_servers), message="server returned no tools or MCP SDK/transport is unavailable")


def build_preloaded_soul_prompt():
    candidates = []
    for raw_path in (
        os.environ.get("OJ_CONTESTANT_SOUL_PATH", ""),
        str(Path(os.environ.get("HERMES_HOME", "")) / "SOUL.md") if os.environ.get("HERMES_HOME") else "",
        str(Path(os.environ.get("HOME", "")) / "SOUL.md") if os.environ.get("HOME") else "",
    ):
        path = str(raw_path or "").strip()
        if path and path not in candidates:
            candidates.append(path)
    for raw_path in candidates:
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        return "\\n\\n".join(
            [
                "## PRELOADED SOUL.md",
                (
                    "The OJ platform preloaded a contestant SOUL.md file for this run. "
                    "Treat it as standing instructions that apply throughout the session."
                ),
                f"Path: {path}",
                text,
            ]
        )
    return ""


def build_selected_skill_index_prompt(skill_names):
    skills_root = Path(os.environ.get("HERMES_HOME") or os.environ.get("HOME") or "/home/hermes") / "skills"
    entries = []
    normalized = []
    missing = []
    for raw_name in skill_names or []:
        skill_name = str(raw_name or "").strip()
        if not skill_name or skill_name in normalized:
            continue
        normalized.append(skill_name)
        skill_dir = skills_root / skill_name
        if not skill_dir.exists() or not skill_dir.is_dir():
            missing.append(skill_name)
            continue
        skill_md = skill_dir / "SKILL.md"
        entry = f"- {skill_name}: {skill_dir}"
        if skill_md.exists():
            entry += f" (inspect {skill_md} if relevant)"
        entries.append(entry)
    if missing:
        return "", normalized, missing
    if not entries:
        return "", normalized, []
    return "\\n\\n".join(
        [
            "## AVAILABLE SKILLS",
            (
                "The OJ platform mounted the skills available for this run under the local filesystem. "
                "Entries may be platform-provided or contestant-selected. "
                "These skills are NOT preloaded into your system prompt."
            ),
            (
                "Treat the list below as a directory index only. "
                "If a skill seems useful, inspect its files on demand before using or describing its contents."
            ),
            "\\n".join(entries),
        ]
    ), normalized, []


def main():
    prompt = Path(prompt_path).read_text(encoding="utf-8")
    parsed_toolsets = _toolsets_list(toolsets)
    _discover_mcp_toolsets(parsed_toolsets)
    cli = HermesCLI(
        model=model,
        toolsets=parsed_toolsets,
        provider=provider,
        max_turns=int(max_turns),
        verbose=False,
        compact=True,
        ignore_rules=True,
    )
    atexit.register(_run_cleanup)

    parsed_skills = _parse_skills_argument(skills)
    if parsed_skills:
        skills_prompt, mounted_skills, missing_skills = build_selected_skill_index_prompt(parsed_skills)
        if missing_skills:
            raise ValueError(f"Unknown skill(s): {', '.join(missing_skills)}")
        if skills_prompt:
            cli.system_prompt = "\\n\\n".join(
                part for part in (cli.system_prompt, skills_prompt) if part
            ).strip()
            cli.selected_skills = mounted_skills
    soul_prompt = build_preloaded_soul_prompt()
    if soul_prompt:
        cli.system_prompt = "\\n\\n".join(
            part for part in (cli.system_prompt, soul_prompt) if part
        ).strip()

    cli.tool_progress_mode = "off"
    if not cli._ensure_runtime_credentials():
        return 1

    turn_route = cli._resolve_turn_agent_config(prompt)
    if turn_route["signature"] != cli._active_agent_route_signature:
        cli.agent = None

    if not cli._init_agent(
        model_override=turn_route["model"],
        runtime_override=turn_route["runtime"],
        request_overrides=turn_route.get("request_overrides"),
    ):
        return 1

    cli.agent.quiet_mode = True
    cli.agent.suppress_status_output = True
    cli.agent.tool_gen_callback = None
    _install_live_callbacks(cli.agent)

    result = cli.agent.run_conversation(
        user_message=prompt,
        conversation_history=cli.conversation_history,
    )
    if getattr(cli.agent, "session_id", None) and cli.agent.session_id != cli.session_id:
        cli.session_id = cli.agent.session_id

    response = result.get("final_response", "") if isinstance(result, dict) else str(result)
    if not response and isinstance(result, dict) and result.get("error") and (result.get("failed") or result.get("partial")):
        print(f"Error: {result['error']}", file=sys.stderr, flush=True)

    print(f"\\nsession_id: {cli.session_id}", file=sys.stderr, flush=True)
    return 1 if isinstance(result, dict) and result.get("failed") else 0


try:
    sys.exit(main())
except Exception as exc:
    _emit("agent.error", message=_compact(str(exc), 1200))
    print(f"Error: {exc}", file=sys.stderr, flush=True)
    sys.exit(1)
"""


def make_hermes_config(base_url, api_key, model, toolset_list):
    mcp_servers = selected_mcp_config(toolset_list)
    return {
        "model": {
            "provider": "custom",
            "default": model,
            "base_url": base_url,
            "api_key": api_key,
            "api_mode": "chat_completions",
        },
        "agent": {
            "max_turns": int(settings.AGENT_MAX_TURNS),
            "reasoning_effort": "medium",
            "disabled_toolsets": ["tts", "image_gen", "web", "browser", "memory"],
        },
        "platform_toolsets": {"cli": toolset_list},
        "mcp_servers": mcp_servers,
        "mcpServers": mcp_servers,
        "terminal": {"backend": "local", "timeout": 180},
        "approvals": {
            "mode": "off" if settings.HERMES_UNATTENDED else "manual",
            "cron_mode": "approve" if settings.HERMES_UNATTENDED else "deny",
            "timeout": 1 if settings.HERMES_UNATTENDED else 60,
            "gateway_timeout": 1 if settings.HERMES_UNATTENDED else 300,
        },
        "compression": {"enabled": False},
    }
def write_env_file(path, values):
    lines = []
    for key, value in values.items():
        if value is None:
            continue
        clean = str(value).replace("\r", "").replace("\n", "")
        lines.append(f"{key}={clean}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def base_runtime_env(home, runtime_config, phase, ssh_identity=None, toolsets=None):
    env = {
        "HERMES_HOME": str(home),
        "HOME": str(home),
        "OJ_CONTESTANT_SOUL_PATH": str(Path(home) / "SOUL.md"),
        "PYTHONPATH": settings.HERMES_CONTAINER_LIB if str(home) == "/home/hermes" else settings.HERMES_LIB,
        "HERMES_SESSION_SOURCE": f"oj-{phase}",
        "OPENAI_API_KEY": runtime_config["api_key"],
        "CUSTOM_BASE_URL": runtime_config["api_base_url"],
        "UV_PYTHON": os.environ.get("OJ_MCP_UV_PYTHON", os.environ.get("UV_PYTHON", "3.12")),
    }
    if ALIBABA_MCP_SERVER_NAME in set(toolsets or []):
        env.update(
            {
                "ALIBABA_CLOUD_ACCESS_KEY_ID": os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", ""),
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET": os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", ""),
                "ALIBABA_CLOUD_REGION_ID": os.environ.get("ALIBABA_CLOUD_REGION_ID", "cn-guangzhou"),
            }
        )
    if RUM_MCP_SERVER_NAME in set(toolsets or []):
        env.update(
            {
                "OJ_RUM_MCP_SECRET_ID": os.environ.get("OJ_RUM_MCP_SECRET_ID", ""),
                "OJ_RUM_MCP_SECRET_KEY": os.environ.get("OJ_RUM_MCP_SECRET_KEY", ""),
            }
        )
    if RUM2_MCP_SERVER_NAME in set(toolsets or []):
        env.update(
            {
                "OJ_RUM2_MCP_SECRET_ID": os.environ.get("OJ_RUM2_MCP_SECRET_ID", ""),
                "OJ_RUM2_MCP_SECRET_KEY": os.environ.get("OJ_RUM2_MCP_SECRET_KEY", ""),
            }
        )
    if MULTI_CLOUD_SSH_MCP_SERVER_NAME in set(toolsets or []):
        aliyun_user = os.environ.get(
            "OJ_MULTI_CLOUD_MCP_ALIYUN_USER",
            os.environ.get("MC_ALIYUN_USER", "ojobserver"),
        )
        tencent_user = os.environ.get(
            "OJ_MULTI_CLOUD_MCP_TENCENT_USER",
            os.environ.get("MC_TENCENT_USER", "ojobserver"),
        )
        env.update(
            {
                "MC_ALIYUN_HOST": os.environ.get("MC_ALIYUN_HOST", "203.0.113.10"),
                "MC_ALIYUN_USER": aliyun_user,
                "OJ_MULTI_CLOUD_MCP_ALIYUN_USER": aliyun_user,
                "MC_ALIYUN_PORT": os.environ.get("MC_ALIYUN_PORT", "22"),
                "MC_TENCENT_HOST": os.environ.get("MC_TENCENT_HOST", "198.51.100.10"),
                "MC_TENCENT_USER": tencent_user,
                "OJ_MULTI_CLOUD_MCP_TENCENT_USER": tencent_user,
                "MC_TENCENT_PORT": os.environ.get("MC_TENCENT_PORT", "22"),
                "MC_ROBOT_APP_DIR": os.environ.get("MC_ROBOT_APP_DIR", "/opt/mc-robot-shop"),
            }
        )
    if settings.HERMES_UNATTENDED:
        env.update({"OJ_HERMES_UNATTENDED": "1", "HERMES_YOLO_MODE": "1", "HERMES_ACCEPT_HOOKS": "1"})
    if ssh_identity:
        env["OJ_SSH_IDENTITY_FILE"] = ssh_identity
        env["MC_SSH_IDENTITY_FILE"] = ssh_identity
    return env


def host_ssh_identity():
    observer_identity = os.environ.get("OJ_MULTI_CLOUD_MCP_IDENTITY_FILE", "").strip()
    if not observer_identity and Path("/root/.ssh/oj_observer_key").exists():
        observer_identity = "/root/.ssh/oj_observer_key"
    return observer_identity


def build_local_command(runner_file, prompt_file, runtime_config, toolsets, skills):
    return [
        settings.HERMES_PYTHON if Path(settings.HERMES_PYTHON).exists() else shutil.which("python3") or "python3",
        str(runner_file),
        settings.HERMES_LIB,
        str(prompt_file),
        "custom",
        runtime_config["model"],
        toolsets,
        skills,
        settings.AGENT_MAX_TURNS,
    ]


def write_contestant_soul(home, soul_md):
    return write_soul_markdown(home, soul_md)
