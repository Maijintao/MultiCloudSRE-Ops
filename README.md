# AIOps OJ Platform

AIOps OJ Platform is a small Python and SQLite evaluation platform for
operations-diagnosis agents. It was built for prompt and skill experiments:
contestants submit a prompt, model endpoint, API key, and optional skills; the
platform runs an isolated Hermes answer attempt and sends the final structured
answer to an OpenAI-compatible grading endpoint.

This public repository is the sanitized open-source edition. It contains the
platform code and three local Example Voting App demo cases. Private competition
cases, real cloud hosts, credentials, hidden answers, and run state should stay
outside the public repository.

## Features

- Single-worker submission queue backed by SQLite.
- Plain Python HTTP server and static frontend.
- Per-submission Hermes run directory with optional Docker isolation.
- Optional contestant skills mounted into `HERMES_HOME/skills`.
- Case format with public `case.json`, private demo `ideal-answer.json`, rubric,
  and optional `inject.sh` / `recover.sh` scripts.
- Streaming submission details for logs, tool calls, answer output, and grading.
- OpenAI-compatible model checks and grading requests.

## Repository Layout

```text
oj_platform/              Python backend modules
static/                   Browser UI and generated static/app.js bundle
static/app/               Frontend source modules
faults/                   Sanitized demo cases
runtime/                  Optional read-only MCP helper runtimes
scripts/build-static-app.js
tests/                    Unit and repository hygiene tests
docs/                     Architecture, deployment, and case authoring notes
```

## Quick Start

Use Python 3.10 or newer.

```bash
cd aiops-platform
python -m unittest discover -s tests -v
PORT=8090 python server.py
```

Open `http://127.0.0.1:8090/`.

Development defaults are intentionally weak and are only for local use:

- username: `admin`
- password: `dev-admin-password`
- invite code: `dev-invite-code`

Set `OJ_ENV=production` before exposing the service. Production mode requires
explicit secrets and grader configuration.

## Configuration

Copy `.env.example` into your deployment environment and fill in real values.
The platform does not automatically load `.env`; use your shell, process
manager, container runtime, or systemd `EnvironmentFile`.

Required for production:

- `OJ_ADMIN_PASSWORD`
- `OJ_REGISTRATION_INVITE_CODE`
- `OJ_JWT_SECRET`
- `OJ_GRADER_BASE_URL`
- `OJ_GRADER_MODEL`
- `OJ_GRADER_API_KEY`

The grader endpoint must expose an OpenAI-compatible
`/chat/completions` API. Contestant model endpoints are configured from user
profiles.

## Frontend Build

The checked-in `static/app.js` file is generated so the app can be served by the
Python HTTP server without a frontend toolchain.

```bash
node scripts/build-static-app.js
```

Edit files under `static/app/`, rebuild, and commit both the source change and
the generated bundle.

## Demo Cases

The public `faults/` directory contains only sanitized Example Voting App demos:

- `db_down`
- `redis_down`
- `worker_down`

These are safe examples of the case shape. Do not commit private competition
cases, real infrastructure addresses, credentials, or hidden answers.

## Docker Runtime

The Hermes runtime image can be built with:

```bash
docker build -t hermes-agent:latest -f docker/hermes-runtime.Dockerfile .
```

If you need an apt mirror, pass one explicitly:

```bash
docker build --build-arg APT_MIRROR=https://mirror.example.org -t hermes-agent:latest -f docker/hermes-runtime.Dockerfile .
```

## Documentation

- [Architecture](docs/architecture.md)
- [Case format](docs/case-format.md)
- [Deployment](docs/deployment.md)
- [Security](docs/security.md)
- [Frontend build](docs/frontend-build.md)
- [Public release](docs/release.md)

## License

MIT
