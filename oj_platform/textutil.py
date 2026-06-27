import shlex

from . import settings


def mask_api_key(api_key):
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return api_key[:2] + "***"
    return api_key[:4] + "***" + api_key[-4:]


def truncate_text(text, limit=None):
    limit = limit or settings.MAX_TRANSCRIPT_CHARS
    text = text or ""
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit] + f"\n\n[output truncated, {omitted} chars omitted]"


def shell_quote_for_log(args):
    redacted = []
    skip_next = False
    for arg in args:
        value = str(arg)
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
            continue
        if value.upper() in settings.SENSITIVE_ENV_KEYS:
            redacted.append(value)
            skip_next = True
            continue
        if any(value.startswith(key + "=") for key in settings.SENSITIVE_ENV_KEYS):
            key = value.split("=", 1)[0]
            redacted.append(key + "=<redacted>")
            continue
        redacted.append(value)
    return " ".join(shlex.quote(item) for item in redacted)

