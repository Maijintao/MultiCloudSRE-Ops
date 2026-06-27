# Architecture

AIOps OJ Platform is intentionally small. The backend is a Python package under
`oj_platform/`, the UI is static HTML/CSS/JavaScript under `static/`, and SQLite
stores users, profiles, submissions, and app settings.

## Runtime Flow

1. A user logs in and configures an OpenAI-compatible answer model endpoint.
2. The user submits a case attempt with a prompt and optional skills.
3. The background worker claims the queued submission.
4. The worker runs the case injection script when one is configured.
5. Hermes receives an isolated run home, workspace, prompt, model profile, and
   skill directory.
6. The answer transcript and final output are recorded as the run streams.
7. The recovery script runs when one is configured.
8. The grading request is sent to the platform-managed OpenAI-compatible
   grading endpoint.

## Main Components

- `server.py` initializes the database, resets interrupted submissions, starts
  the worker, and serves HTTP.
- `oj_platform/http_app.py` handles API routes and static files.
- `oj_platform/worker.py` performs the submission state machine.
- `oj_platform/hermes_runner.py` and `oj_platform/hermes_docker.py` build the
  Hermes command and optional Docker isolation.
- `oj_platform/cases.py` loads and edits case files.
- `oj_platform/grading_api.py` streams grading responses.

## Data Boundary

The public case API exposes `case.json` fields only. `ideal-answer.json` and
rubrics are server-side scoring material. In a public repository, include only
demo answers you are comfortable publishing.
