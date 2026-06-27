import base64
import hashlib
import hmac
import json
import secrets

from . import settings
from .timeutil import utc_timestamp


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(data):
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def get_jwt_secret():
    settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
    secret_file = settings.STATE_DIR / "jwt_secret"
    secret = settings.JWT_SECRET_ENV
    if secret:
        return secret.encode("utf-8")
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try:
            secret_file.chmod(0o600)
        except OSError:
            pass
    return secret_file.read_text(encoding="utf-8").strip().encode("utf-8")


JWT_SECRET = get_jwt_secret()


def hash_password(password, salt=None, iterations=260000):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(iterations, b64url(salt), b64url(digest))


def verify_password(password, encoded):
    try:
        scheme, iterations, salt, digest = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hash_password(password, b64url_decode(salt), int(iterations)).split("$", 3)[3]
        return hmac.compare_digest(candidate, digest)
    except Exception:
        return False


def make_token(user):
    now = utc_timestamp()
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "iat": now,
        "exp": now + settings.JWT_TTL_SECONDS,
        "jti": secrets.token_urlsafe(16),
    }
    signing_input = "{}.{}".format(
        b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    )
    signature = hmac.new(JWT_SECRET, signing_input.encode("ascii"), hashlib.sha256).digest()
    return "{}.{}".format(signing_input, b64url(signature))


def verify_token(token):
    try:
        header_part, payload_part, signature_part = token.split(".", 2)
        signing_input = f"{header_part}.{payload_part}"
        expected = hmac.new(JWT_SECRET, signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(b64url(expected), signature_part):
            return None
        payload = json.loads(b64url_decode(payload_part).decode("utf-8"))
        if int(payload.get("exp", 0)) < utc_timestamp():
            return None
        return payload
    except Exception:
        return None
