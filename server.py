#!/usr/bin/env python3
from http.server import ThreadingHTTPServer

from oj_platform import db, settings
from oj_platform.cases import load_cases_list
from oj_platform.hermes_runner import agent_status
from oj_platform.http_app import Handler
from oj_platform.submissions import reset_interrupted_submissions
from oj_platform.worker import start_worker


class OJThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = settings.HTTP_REQUEST_QUEUE_SIZE


def main():
    if not settings.FAULTS_DIR.exists() or not load_cases_list():
        raise SystemExit(f"no cases found below {settings.FAULTS_DIR}")
    db.init_db()
    reset_interrupted_submissions()
    start_worker()
    server = OJThreadingHTTPServer(("0.0.0.0", settings.PORT), Handler)
    print(f"AIOps OJ platform listening on 0.0.0.0:{settings.PORT}")
    print(f"HTTP request queue size: {settings.HTTP_REQUEST_QUEUE_SIZE}")
    print(f"Environment: {settings.ENVIRONMENT}")
    if not settings.IS_PRODUCTION:
        print(
            "WARNING: development defaults are enabled. "
            "Set OJ_ENV=production and configure secrets before exposing this service."
        )
    print(f"Database: {settings.DB_FILE}")
    print(f"Hermes: {agent_status()}")
    server.serve_forever()


if __name__ == "__main__":
    main()
