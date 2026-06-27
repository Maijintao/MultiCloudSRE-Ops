# Deployment

This project can run directly with Python for demos. Production-like deployments
should use explicit environment variables, a process manager, and Hermes Docker
isolation.

## Local Demo

```bash
python -m unittest discover -s tests -v
PORT=8090 python server.py
```

## Production Checklist

Set at least:

```bash
OJ_ENV=production
OJ_ADMIN_USERNAME=admin
OJ_ADMIN_PASSWORD=<long-random-password>
OJ_REGISTRATION_INVITE_CODE=<private-invite-code>
OJ_JWT_SECRET=<long-random-secret>
OJ_GRADER_BASE_URL=https://api.example.com/v1
OJ_GRADER_MODEL=<grader-model>
OJ_GRADER_API_KEY=<grader-key>
OJ_HERMES_DOCKER=1
OJ_HERMES_DOCKER_IMAGE=hermes-agent:latest
```

Use `.env.example` as the complete reference.

## Systemd

The sample unit is `systemd/oj-platform.service`. It expects the application at
`/opt/oj-platform` and reads optional settings from `/etc/oj-platform.env`.

```bash
cp systemd/oj-platform.service /etc/systemd/system/oj-platform.service
systemctl daemon-reload
systemctl enable --now oj-platform
```

## State

Runtime state belongs under `state/` by default and is ignored by Git. Back it
up separately if you need to preserve users or submissions.
