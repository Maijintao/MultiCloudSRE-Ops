# Security Policy

This repository is a research and teaching platform. Treat it as an application
that executes untrusted prompts and optional user-provided skill text.

## Reporting

Please report vulnerabilities privately to the maintainers before publishing
details. Include reproduction steps, affected commit or release, and any known
workarounds.

## Deployment Notes

- Set `OJ_ENV=production` for public or shared deployments.
- In production, configure `OJ_ADMIN_PASSWORD`, `OJ_REGISTRATION_INVITE_CODE`,
  `OJ_JWT_SECRET`, `OJ_GRADER_BASE_URL`, `OJ_GRADER_MODEL`, and
  `OJ_GRADER_API_KEY` explicitly.
- Do not commit `.env`, SQLite databases, run state, kubeconfigs, SSH keys,
  API keys, public cloud hostnames tied to a private lab, or hidden answer files
  from non-demo competitions.
- Prefer Docker isolation for Hermes answer runs.
