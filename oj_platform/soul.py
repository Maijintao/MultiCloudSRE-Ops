from pathlib import Path

from . import settings


def normalize_soul_markdown(value, max_chars=None):
    limit = int(max_chars or settings.MAX_SOUL_CHARS)
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > limit:
        raise ValueError(f"SOUL.md is too long, max {limit} chars")
    return text if text.strip() else ""


def soul_configured(value):
    return bool(normalize_soul_markdown(value))


def load_default_soul_markdown():
    path = Path(settings.DEFAULT_SOUL_FILE)
    if not path.exists() or not path.is_file():
        return ""
    return normalize_soul_markdown(path.read_text(encoding="utf-8"))


def effective_soul_markdown(value):
    custom = normalize_soul_markdown(value)
    if custom:
        return custom
    return load_default_soul_markdown()


def write_soul_markdown(home, soul_md):
    text = effective_soul_markdown(soul_md)
    if not text:
        return None
    target = Path(home) / "SOUL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    return target
