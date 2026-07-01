import os

from . import settings
from .cases import resolve_case_script
from .processes import run_streamed_process
from .submissions import append_submission_log
from .textutil import shell_quote_for_log, truncate_text
from .timeutil import utc_now


def run_case_script(submission_id, case, action):
    key = "inject_script" if action == "inject" else "recover_script"
    script = resolve_case_script(case, key)
    if not script:
        append_submission_log(submission_id, f"[{utc_now()}] {action}: no script configured, skipped.\n")
        return {"ok": True, "returncode": 0, "stdout": "", "stderr": ""}

    append_submission_log(submission_id, f"[{utc_now()}] {action}: starting {script.name}\n")
    env = os.environ.copy()
    env["OJ_CASE_ID"] = str(case.get("id", ""))
    env["OJ_FAULT_ACTION"] = action
    env["PATH"] = "/root/.local/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")

    suppress_detailed_output = action in {"inject", "recover"}
    output_counts = {"stdout": 0, "stderr": 0}

    def on_output(stream_name, line):
        output_counts[stream_name] = output_counts.get(stream_name, 0) + 1
        if suppress_detailed_output:
            return
        append_submission_log(submission_id, f"[{utc_now()}] {action}/{stream_name}: {line}")

    cmd = ["bash", str(script)]
    result = run_streamed_process(
        cmd,
        cwd=settings.ROOT,
        env=env,
        timeout=settings.FAULT_SCRIPT_TIMEOUT_SECONDS,
        on_output=on_output,
    )
    if suppress_detailed_output:
        if result["returncode"] == 0:
            append_submission_log(submission_id, f"[{utc_now()}] {action}: completed successfully\n")
        else:
            append_submission_log(
                submission_id,
                f"[{utc_now()}] {action}: failed (details suppressed; stderr lines={output_counts['stderr']})\n",
            )
    append_submission_log(submission_id, f"[{utc_now()}] {action}: finished with returncode {result['returncode']}\n")
    result["ok"] = result["returncode"] == 0
    if suppress_detailed_output:
        stdout_summary = "suppressed"
        stderr_excerpt = truncate_text((result["stderr"] or "").strip(), 1200)
        stderr_summary = stderr_excerpt if stderr_excerpt else "suppressed"
        result["transcript"] = truncate_text(
            f"$ {shell_quote_for_log(cmd)}\n"
            f"started_at: {result['started']}\n"
            f"finished_at: {result['finished']}\n"
            f"returncode: {result['returncode']}\n"
            f"stdout_lines: {output_counts['stdout']}\n"
            f"stderr_lines: {output_counts['stderr']}\n\n"
            f"--- stdout ---\n{stdout_summary}\n\n--- stderr ---\n{stderr_summary}"
        )
    else:
        result["transcript"] = truncate_text(
            f"$ {shell_quote_for_log(cmd)}\n"
            f"started_at: {result['started']}\n"
            f"finished_at: {result['finished']}\n"
            f"returncode: {result['returncode']}\n\n"
            f"--- stdout ---\n{result['stdout']}\n\n--- stderr ---\n{result['stderr']}"
        )
    return result
