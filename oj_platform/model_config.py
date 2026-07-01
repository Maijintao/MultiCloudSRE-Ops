import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import settings
from .grader_config import save_platform_grader_config
from .textutil import mask_api_key
from .users import effective_grader_profile, get_user_profile, update_user_profile_fields


def request_headers(api_key, content_type=None):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": settings.MODEL_CHECK_USER_AGENT,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def detect_model(base_url, api_key):
    if settings.DEFAULT_MODEL and settings.DEFAULT_MODEL.lower() != "auto":
        return settings.DEFAULT_MODEL
    try:
        request = Request(
            base_url.rstrip("/") + "/models",
            headers=request_headers(api_key),
        )
        with urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
        models = data.get("data") or []
        if models and models[0].get("id"):
            return models[0]["id"]
    except Exception:
        pass
    return "gpt-4o-mini"


def model_check_fields(payload, existing=None):
    existing = existing or {}
    base_url = str(payload.get("base_url", existing.get("api_base_url") or "")).strip().rstrip("/")
    api_key = str(payload.get("api_key", "") or "").strip() or str(existing.get("api_key") or "").strip()
    model = str(payload.get("model", existing.get("model") or "")).strip()
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise ValueError("base url must start with http:// or https://")
    if not api_key:
        raise ValueError("api key is required")
    if not model or model.lower() == "auto":
        model = detect_model(base_url, api_key)
    return base_url, api_key, model


def check_model_available(base_url, api_key, model):
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "temperature": 0,
            "stream": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers=request_headers(api_key, "application/json"),
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            raw = response.read(2048).decode("utf-8", errors="replace")
        return {"ok": True, "message": "model is available", "model": model, "status": response.status, "sample": raw[:500]}
    except HTTPError as exc:
        raw = exc.read(2048).decode("utf-8", errors="replace")
        detail = raw.strip()[:500] or exc.reason
        return {"ok": False, "message": f"model check failed: HTTP {exc.code} {detail}", "model": model, "status": exc.code}
    except URLError as exc:
        return {"ok": False, "message": f"model check failed: {exc.reason}", "model": model}
    except Exception as exc:
        return {"ok": False, "message": f"model check failed: {exc}", "model": model}


def validate_profile_payload(payload, existing=None):
    existing = existing or {}
    submitted_key = str(payload.get("api_key", "") or "").strip()
    base_url, api_key, model = model_check_fields(payload, existing)
    fields = {"api_base_url": base_url, "model": model}
    if submitted_key:
        fields["api_key"] = submitted_key
        fields["api_key_mask"] = mask_api_key(submitted_key)
    elif not existing.get("api_key_mask"):
        fields["api_key_mask"] = mask_api_key(api_key)
    return fields


def update_user_profile(user, payload):
    existing = get_user_profile(user["id"])
    base_url, api_key, model = model_check_fields(payload, existing)
    check = check_model_available(base_url, api_key, model)
    if not check.get("ok"):
        raise ValueError(check.get("message") or "model is unavailable")
    fields = validate_profile_payload(payload, existing)
    return update_user_profile_fields(user["id"], fields)


def check_grader_model_available(api_key):
    profile = effective_grader_profile({}, include_secret=True)
    platform_api_key = str(api_key or profile.get("api_key") or "").strip()
    if not platform_api_key:
        raise ValueError("platform scoring API is not configured")
    return check_model_available(profile["api_base_url"], platform_api_key, profile["model"])


def check_grader_profile_available(payload, existing=None):
    payload = payload or {}
    existing = effective_grader_profile({}, include_secret=True)
    base_url, api_key, model = model_check_fields(payload, existing)
    return check_model_available(base_url, api_key, model)


def validate_platform_grader_payload(payload):
    existing = effective_grader_profile({}, include_secret=True)
    submitted_key = str((payload or {}).get("api_key", "") or "").strip()
    base_url, api_key, model = model_check_fields(payload or {}, existing)
    return {
        "api_base_url": base_url,
        "api_key": submitted_key or api_key,
        "api_key_mask": mask_api_key(submitted_key or api_key),
        "model": model,
    }


def update_platform_grader_config(payload):
    fields = validate_platform_grader_payload(payload)
    check = check_model_available(fields["api_base_url"], fields["api_key"], fields["model"])
    if not check.get("ok"):
        raise ValueError(check.get("message") or "model is unavailable")
    return save_platform_grader_config(fields)


def public_grader_config(profile=None):
    effective = effective_grader_profile(profile)
    return {
        "api_base_url": effective["api_base_url"],
        "api_key_mask": effective["api_key_mask"],
        "model": effective["model"],
        "configured": effective["configured"],
        "source": effective["source"],
        "label": settings.GRADER_LABEL,
        "managed": True,
    }


def update_user_grader_config(user, payload):
    raise ValueError("scoring API is managed by the platform and cannot be edited")


def require_submission_grader_config(submission):
    api_key = str(submission.get("grader_api_key") or "").strip()
    base_url = str(submission.get("grader_base_url") or "").strip().rstrip("/")
    model = str(submission.get("grader_model") or "").strip()
    if not (api_key and base_url and model):
        profile = effective_grader_profile({}, include_secret=True)
        api_key = api_key or str(profile.get("api_key") or "").strip()
        base_url = base_url or str(profile.get("api_base_url") or "").strip().rstrip("/")
        model = model or str(profile.get("model") or "").strip()
    if not api_key:
        raise ValueError("platform scoring API is not configured")
    return {
        "api_base_url": base_url,
        "api_key": api_key,
        "model": model,
    }
