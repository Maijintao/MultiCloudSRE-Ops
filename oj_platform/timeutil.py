from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_timestamp():
    return int(datetime.now(timezone.utc).timestamp())
