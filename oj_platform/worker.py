import json
import threading
import time

from . import settings
from .cases import load_cases_map
from .faults import run_case_script
from .grading import extract_json_object, has_meaningful_agent_output, normalize_score, verdict_for_score
from .grading_api import stream_grading_completion
from .hermes_runner import run_hermes
from .hermes_transcript import summarize_agent_failure
from .mcp import answer_mcp_servers
from .model_config import require_submission_grader_config
from .prompts import build_grade_messages
from .submissions import append_submission_log, claim_next_submission, update_submission
from .timeutil import utc_now


def answer_runtime_config(submission):
    return {
        "api_base_url": submission["api_base_url"],
        "api_key": submission["api_key"],
        "model": submission["model"],
    }


def start_parallel_recover(submission_id, case):
    state = {"result": None, "error": None}

    def target():
        try:
            result = run_case_script(submission_id, case, "recover")
            state["result"] = result
            if result["ok"]:
                append_submission_log(submission_id, f"[{utc_now()}] recover: completed while scoring continued\n")
            else:
                append_submission_log(submission_id, f"[{utc_now()}] recover: failed while scoring continued\n")
        except Exception as exc:
            state["error"] = str(exc)
            append_submission_log(submission_id, f"[{utc_now()}] recover: exception while scoring continued: {exc}\n")

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, state


def wait_parallel_recover(thread, state):
    thread.join()
    if state.get("error"):
        return {"ok": False, "error": state["error"], "transcript": None}
    return state.get("result") or {"ok": False, "error": "fault recovery returned no result", "transcript": None}


def fail_submission(submission_id, error, **fields):
    update_submission(
        submission_id,
        status="failed",
        error=error,
        finished_at=utc_now(),
        api_key=None,
        grader_api_key=None,
        **fields,
    )


def finalize_grade_outcome(submission_id, grade, recover):
    grade_json = extract_json_object(grade.get("stdout", ""))
    score = normalize_score((grade_json or {}).get("total_score"))
    summary = (grade_json or {}).get("analysis_summary") or ""
    recovered = bool(recover.get("ok"))
    final_score = score if recovered else None
    verdict = verdict_for_score(final_score)
    grade_error = None
    if not grade.get("ok"):
        grade_error = grade.get("error") or "scoring API request failed"
    elif score is None:
        grade_error = "scoring API returned no valid total_score; check the API output"
    if not recovered:
        recover_error = recover.get("error") or "fault recovery failed; see process log"
        grade_error = f"{grade_error}; {recover_error}" if grade_error else recover_error
    update_submission(
        submission_id,
        status="done" if grade.get("ok") and score is not None and recovered else "failed",
        grade_transcript=grade.get("transcript"),
        grade_output=grade.get("display") or grade.get("stdout", ""),
        grade_json=json.dumps(grade_json, ensure_ascii=False, indent=2) if grade_json else None,
        score=final_score,
        verdict=verdict,
        result_summary=str(summary)[:1000],
        error=grade_error,
        finished_at=utc_now(),
        api_key=None,
        grader_api_key=None,
    )


def run_background_grading(submission, case, answer, recover_thread, recover_state):
    submission_id = submission["id"]
    try:
        grader = require_submission_grader_config(submission)
        grade_messages = build_grade_messages(case, answer["stdout"], answer["transcript"])
        grade = stream_grading_completion(
            submission_id,
            grade_messages,
            grader,
            settings.JUDGE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        error = f"scoring API failed: {exc}"
        append_submission_log(submission_id, f"[{utc_now()}] grade-api: {error}\n")
        grade = {"ok": False, "stdout": "", "display": "", "transcript": None, "error": error}

    try:
        recover = wait_parallel_recover(recover_thread, recover_state)
    except Exception as exc:
        append_submission_log(submission_id, f"[{utc_now()}] recover: wait failed while grading continued: {exc}\n")
        recover = {"ok": False, "error": str(exc), "transcript": None}

    try:
        finalize_grade_outcome(submission_id, grade, recover)
    except Exception as exc:
        fail_submission(
            submission_id,
            f"background grading finalization failed: {exc}",
            grade_transcript=grade.get("transcript"),
            grade_output=grade.get("display") or grade.get("stdout", ""),
        )


def start_background_grading(submission, case, answer, recover_thread, recover_state):
    thread = threading.Thread(
        target=run_background_grading,
        args=(submission, case, answer, recover_thread, recover_state),
        daemon=False,
    )
    thread.start()
    return thread


def run_submission(submission):
    cases = load_cases_map()
    case = cases.get(submission["case_id"])
    if not case:
        fail_submission(submission["id"], "case not found")
        return

    injected = False
    recovered = False
    recover_thread = None
    recover_state = None
    background_grading = False
    try:
        update_submission(submission["id"], status="injecting")
        inject = run_case_script(submission["id"], case, "inject")
        if not inject["ok"]:
            fail_submission(
                submission["id"],
                "fault injection failed; see process log",
                answer_transcript=inject.get("transcript"),
            )
            return
        injected = True

        update_submission(submission["id"], status="answering")
        answer_prompt = submission["prompt"]
        answer = run_hermes(
            submission,
            "answer",
            answer_prompt,
            answer_runtime_config(submission),
            settings.AGENT_TIMEOUT_SECONDS,
            skill_text=submission.get("skill", ""),
            skills_json=submission.get("skills_json", ""),
            soul_md=submission.get("soul_md", ""),
            toolsets=settings.HERMES_TOOLSETS,
            required_mcp_servers=answer_mcp_servers(case=case, submission=submission),
        )
        update_submission(
            submission["id"],
            answer_transcript=answer["transcript"],
            answer_output=answer["stdout"],
            answer_returncode=answer["returncode"],
        )

        answer_has_output = has_meaningful_agent_output(answer["stdout"])
        if not answer["ok"] or not answer_has_output:
            update_submission(submission["id"], status="recovering")
            recover = run_case_script(submission["id"], case, "recover")
            recovered = recover["ok"]
        else:
            update_submission(submission["id"], status="recovering")
            append_submission_log(submission["id"], f"[{utc_now()}] recover+grade: started in parallel\n")
            recover_thread, recover_state = start_parallel_recover(submission["id"], case)
            update_submission(submission["id"], status="grading")
            start_background_grading(submission, case, answer, recover_thread, recover_state)
            background_grading = True
            recover = wait_parallel_recover(recover_thread, recover_state)
            recovered = recover["ok"]
            append_submission_log(
                submission["id"],
                (
                    f"[{utc_now()}] worker: recovery finished; grading no longer blocks the queue\n"
                    if recovered
                    else f"[{utc_now()}] worker: recovery finished with failure; grading will mark the submission failed\n"
                ),
            )
            return

        if not recovered:
            fail_submission(
                submission["id"],
                "fault recovery failed; grading skipped",
                grade_transcript=recover.get("transcript"),
            )
            return

        if not answer["ok"]:
            fail_submission(
                submission["id"],
                summarize_agent_failure(answer["returncode"], answer.get("stderr", "")),
            )
            return
        if not answer_has_output:
            fail_submission(submission["id"], "answer agent returned empty output; check contestant model config")
            return
    except Exception as exc:
        if background_grading:
            append_submission_log(
                submission["id"],
                f"[{utc_now()}] worker: main pipeline exited after handing grading to background: {exc}\n",
            )
            return
        if recover_thread:
            try:
                recover = wait_parallel_recover(recover_thread, recover_state)
                recovered = recover["ok"]
            except Exception as recover_exc:
                append_submission_log(submission["id"], f"[{utc_now()}] recover failed after exception: {recover_exc}\n")
        elif injected and not recovered:
            try:
                update_submission(submission["id"], status="recovering")
                recover = run_case_script(submission["id"], case, "recover")
                recovered = recover["ok"]
            except Exception as recover_exc:
                append_submission_log(submission["id"], f"[{utc_now()}] recover failed after exception: {recover_exc}\n")
        fail_submission(submission["id"], str(exc))


def worker_loop():
    while True:
        try:
            submission = claim_next_submission()
            if not submission:
                time.sleep(2)
                continue
            run_submission(submission)
        except Exception as exc:
            print(f"[{utc_now()}] worker error: {exc}", flush=True)
            time.sleep(5)


def start_worker():
    worker = threading.Thread(target=worker_loop, daemon=True)
    worker.start()
    return worker
