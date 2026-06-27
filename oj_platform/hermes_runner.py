import json
import os
import shutil
import threading
import time
from pathlib import Path

from . import settings
from .hermes_docker import agent_status, build_docker_command
from .mcp import ALIBABA_MCP_SERVER_NAME
from .hermes_setup import (
    RUNNER_SCRIPT,
    base_runtime_env,
    build_local_command,
    host_ssh_identity,
    make_hermes_config,
    write_contestant_soul,
    write_env_file,
)
from .skills import write_contestant_skills, write_platform_skills
from .hermes_transcript import (
    read_hermes_conversation,
)
from .processes import run_streamed_process
from .submissions import append_submission_log, update_submission
from .textutil import shell_quote_for_log, truncate_text
from .timeutil import utc_now


OJ_EVENT_PREFIX = "__OJ_EVENT__ "


def should_forward_hermes_log(line):
    ignored = (
        "tools.registry: Could not import tool module tools.browser_dialog_tool",
        "agent.conversation_loop: API call #",
        "agent.tool_executor: tool terminal completed",
        "tools.terminal_tool: Creating new local environment",
        "tools.terminal_tool: local environment ready",
        "tools.environments.base: Session snapshot created",
        "mcp.client.streamable_http: Session termination failed: cannot schedule new futures after shutdown",
    )
    if any(item in line for item in ignored):
        return False
    patterns = (
        "API call failed",
        "Tool terminal returned error",
        "BLOCKED",
        "Denied",
        "denied",
        "approval",
        "DANGEROUS COMMAND",
        "PermissionDeniedError",
        " ERROR ",
        " WARNING ",
    )
    return any(pattern in line for pattern in patterns)


def _compact_live_text(value, limit=1200):
    text = "" if value is None else str(value)
    text = text.replace("\r", "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = " / ".join(lines)
    if len(text) > limit:
        text = text[:limit].rstrip() + "...[truncated]"
    return text


def format_runner_event(line, live_prefix):
    raw = line[len(OJ_EVENT_PREFIX) :].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    event = payload.get("event")
    tool = _compact_live_text(payload.get("tool"), 120) or "unknown"
    if event == "tool.started":
        preview = _compact_live_text(payload.get("preview"), 180)
        suffix = f": {preview}" if preview else ""
        return f"[{utc_now()}] {live_prefix}/tool-call: 调用工具 {tool}{suffix}\n"
    if event == "tool.completed":
        summary = _compact_live_text(payload.get("summary"), 240)
        duration = payload.get("duration")
        duration_text = f" ({duration}s)" if duration is not None else ""
        suffix = f": {summary}" if summary else ""
        return f"[{utc_now()}] {live_prefix}/tool-result: 返回摘要 {tool}{duration_text}{suffix}\n"
    if event == "stage.message":
        summary = _compact_live_text(payload.get("summary"), 600)
        return f"[{utc_now()}] {live_prefix}/stage: {summary}\n"
    if event == "mcp.ready":
        count = payload.get("tool_count", 0)
        server = _compact_live_text(payload.get("server"), 120) or "MCP"
        return f"[{utc_now()}] {live_prefix}/mcp: {server} ready ({count} tools)\n"
    if event == "mcp.error":
        message = _compact_live_text(payload.get("message"), 360)
        server = _compact_live_text(payload.get("server"), 120) or "MCP"
        return f"[{utc_now()}] {live_prefix}/error: {server} unavailable: {message}\n"
    if event == "stage.conclusion":
        return ""
    if event == "agent.error":
        message = _compact_live_text(payload.get("message"), 1200)
        return f"[{utc_now()}] {live_prefix}/error: 运行错误: {message}\n"
    return ""


def prepare_run_root(submission, phase, prompt, runtime_config, toolsets, skill_text, skills_json, soul_md):
    run_root = settings.STATE_DIR / "hermes_runs" / str(submission["id"]) / phase
    if run_root.exists():
        shutil.rmtree(run_root, ignore_errors=True)
    home = run_root / "home"
    workspace = run_root / "workspace"
    prompt_file = run_root / "prompt.txt"
    runner_file = run_root / "run_hermes_query.py"
    env_file = run_root / "container.env"
    home.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        home.chmod(0o700)
    except OSError:
        pass

    toolset_list = settings.normalize_toolsets(toolsets).split(",")
    if "k3s-cluster" in toolset_list:
        (home / ".kube").mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(
        json.dumps(
            make_hermes_config(runtime_config["api_base_url"], runtime_config["api_key"], runtime_config["model"], toolset_list),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    prompt_file.write_text(prompt, encoding="utf-8")
    runner_file.write_text(RUNNER_SCRIPT, encoding="utf-8")
    skills = ""
    if phase == "answer":
        platform_skills = write_platform_skills(home, toolset_list)
        contestant_skills = write_contestant_skills(
            home,
            skill_text,
            skills_json,
            reserved_names=platform_skills,
        )
        skill_names = [*platform_skills, *[name for name in contestant_skills.split(",") if name]]
        skills = ",".join(skill_names)
        write_contestant_soul(home, soul_md)

    identity = host_ssh_identity()
    docker_identity = "/run/secrets/oj_ssh_key" if identity and Path(identity).exists() else None
    env_home = "/home/hermes" if settings.HERMES_DOCKER_ENABLED else home
    write_env_file(env_file, base_runtime_env(env_home, runtime_config, phase, docker_identity, toolset_list))
    return run_root, home, workspace, prompt_file, runner_file, env_file, skills


def build_command(run_root, home, workspace, runner_file, prompt_file, env_file, runtime_config, toolsets, skills):
    if settings.HERMES_DOCKER_ENABLED:
        cmd, container_name = build_docker_command(home, workspace, runner_file, prompt_file, env_file, runtime_config, toolsets, skills)
        return cmd, "docker", container_name
    cmd = build_local_command(runner_file, prompt_file, runtime_config, toolsets, skills)
    return cmd, "local", ""


def logged_hermes_command(runtime_config, phase, toolsets, skills):
    logged = [
        settings.HERMES_BIN,
        "chat",
        "--provider",
        "custom",
        "--model",
        runtime_config["model"],
        "--toolsets",
        toolsets,
        "--max-turns",
        settings.AGENT_MAX_TURNS,
        "--source",
        f"oj-{phase}",
        "--ignore-rules",
        "-q",
        "<prompt-file>",
    ]
    if skills:
        logged.extend(["--skills", skills])
    return logged


def run_hermes(
    submission,
    phase,
    prompt,
    runtime_config,
    timeout,
    skill_text="",
    skills_json="",
    soul_md="",
    toolsets=None,
    required_mcp_servers=None,
):
    toolsets = toolsets or settings.HERMES_TOOLSETS
    if phase == "answer":
        answer_toolsets = [item.strip() for item in toolsets.split(",") if item.strip()]
        servers = [ALIBABA_MCP_SERVER_NAME] if required_mcp_servers is None else required_mcp_servers
        for server in servers:
            if server not in answer_toolsets:
                answer_toolsets.append(server)
        toolsets = ",".join(answer_toolsets)
    runtime_config = dict(runtime_config, submission_id=submission["id"], phase=phase)
    run_root, home, workspace, prompt_file, runner_file, env_file, skills = prepare_run_root(
        submission,
        phase,
        prompt,
        runtime_config,
        toolsets,
        skill_text,
        skills_json,
        soul_md,
    )
    cmd, runner_kind, container_name = build_command(
        run_root,
        home,
        workspace,
        runner_file,
        prompt_file,
        env_file,
        runtime_config,
        toolsets,
        skills,
    )

    phase_field = "answer_transcript" if phase == "answer" else "grade_transcript"
    live_prefix = "answer" if phase == "answer" else "grade"
    logged_cmd = logged_hermes_command(runtime_config, phase, toolsets, skills)
    append_submission_log(
        submission["id"],
        f"[{utc_now()}] {live_prefix}: starting Hermes runner={runner_kind} model={runtime_config['model']} toolsets={toolsets}\n",
    )
    update_submission(
        submission["id"],
        runner_kind=runner_kind,
        runner_meta=json.dumps({"container": container_name, "image": settings.HERMES_DOCKER_IMAGE}, ensure_ascii=False),
    )

    live_parts = [f"$ {shell_quote_for_log(logged_cmd)}\n", f"started_at: {utc_now()}\n\n"]
    agent_log_file = home / "logs" / "agent.log"
    last_update = 0

    def on_output(stream_name, line):
        nonlocal last_update
        if not line.strip():
            return
        if line.startswith(OJ_EVENT_PREFIX):
            entry = format_runner_event(line, live_prefix)
            if not entry:
                return
        else:
            entry = f"[{utc_now()}] {live_prefix}/{stream_name}: {line}"
        live_parts.append(entry)
        append_submission_log(submission["id"], entry)
        now = time.monotonic()
        if now - last_update > 1:
            update_submission(submission["id"], **{phase_field: truncate_text("".join(live_parts))})
            last_update = now

    stop_tail = threading.Event()
    log_tail_thread = threading.Thread(target=_tail_agent_log, args=(stop_tail, agent_log_file, submission["id"], live_prefix), daemon=True)
    log_tail_thread.start()

    try:
        env = os.environ.copy()
        if not settings.HERMES_DOCKER_ENABLED:
            env.update(base_runtime_env(home, runtime_config, phase, host_ssh_identity(), toolsets.split(",")))
            env["PATH"] = "/root/.local/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
        result = run_streamed_process(cmd, cwd=run_root, env=env, timeout=timeout, on_output=on_output)
        conversation, final_assistant = read_hermes_conversation(home)
        transcript = (
            f"$ {shell_quote_for_log(logged_cmd)}\n"
            f"started_at: {result['started']}\n"
            f"finished_at: {result['finished']}\n"
            f"returncode: {result['returncode']}\n\n"
            f"--- stdout ---\n{result['stdout'] or ''}\n\n--- stderr ---\n{result['stderr'] or ''}"
            f"\n\n--- hermes conversation ---\n{conversation}"
        )
        return {
            "ok": result["returncode"] == 0,
            "returncode": result["returncode"],
            "stdout": truncate_text(final_assistant or result["stdout"] or ""),
            "stderr": truncate_text(result["stderr"] or ""),
            "transcript": truncate_text(transcript),
        }
    finally:
        stop_tail.set()
        log_tail_thread.join(timeout=2)
        append_submission_log(submission["id"], f"[{utc_now()}] {live_prefix}: Hermes process finished or stopped\n")
        if os.environ.get("OJ_KEEP_HERMES_RUNS", "0") != "1":
            shutil.rmtree(run_root, ignore_errors=True)


def _tail_agent_log(stop_tail, agent_log_file, submission_id, live_prefix):
    position = 0
    while not stop_tail.is_set():
        try:
            if agent_log_file.exists():
                with agent_log_file.open("r", encoding="utf-8", errors="replace") as log_file:
                    log_file.seek(position)
                    for line in log_file:
                        if should_forward_hermes_log(line):
                            append_submission_log(submission_id, f"[{utc_now()}] {live_prefix}/log: {line}")
                    position = log_file.tell()
        except Exception:
            pass
        stop_tail.wait(1.5)
