import subprocess
import threading
import time

from .timeutil import utc_now


def run_streamed_process(cmd, cwd, env, timeout, on_output=None):
    started = utc_now()
    started_monotonic = time.monotonic()
    stdout_parts = []
    stderr_parts = []
    timed_out = False

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )

    def reader(stream, sink, stream_name):
        try:
            for line in iter(stream.readline, ""):
                sink.append(line)
                if on_output:
                    on_output(stream_name, line)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    stdout_thread = threading.Thread(target=reader, args=(proc.stdout, stdout_parts, "stdout"), daemon=True)
    stderr_thread = threading.Thread(target=reader, args=(proc.stderr, stderr_parts, "stderr"), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    while proc.poll() is None:
        if time.monotonic() - started_monotonic > timeout:
            timed_out = True
            proc.kill()
            break
        time.sleep(0.2)

    returncode = proc.wait()
    stdout_thread.join(timeout=3)
    stderr_thread.join(timeout=3)
    stdout = "".join(stdout_parts)
    stderr = "".join(stderr_parts)
    if timed_out:
        returncode = 124
        stderr = f"Timed out after {timeout}s\n{stderr}"

    return {
        "started": started,
        "finished": utc_now(),
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
    }

