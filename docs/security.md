# Security Notes

The platform runs agent prompts and optional user-provided skills. Treat it as
an untrusted execution system.

## Required Production Settings

`OJ_ENV=production` requires:

- `OJ_ADMIN_PASSWORD`
- `OJ_REGISTRATION_INVITE_CODE`
- `OJ_JWT_SECRET`
- `OJ_GRADER_BASE_URL`
- `OJ_GRADER_MODEL`
- `OJ_GRADER_API_KEY`

Development defaults are printed as a warning at startup and should never be
used on a public network.

## Repository Hygiene

Do not commit:

- `.env` or real process environment files.
- SQLite databases or `state/` contents.
- SSH keys, kubeconfigs, tokens, API keys, or cloud credentials.
- Real lab hostnames or IP addresses.
- Private competition `ideal-answer.json`, rubrics, or fault scripts.

The test suite includes a hygiene test for common leaks.

## Runtime Isolation

Use Docker isolation for Hermes runs when contestants are untrusted. Mount only
the run home, empty workspace, prompt, runner, Hermes runtime, and explicitly
approved read-only secrets.
