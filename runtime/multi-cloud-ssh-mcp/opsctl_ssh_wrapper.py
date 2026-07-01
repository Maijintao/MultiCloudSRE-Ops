#!/usr/bin/env python3
"""Forced-command gate for the root-owned read-only opsctl dispatcher."""

import os
import re
import shlex
import subprocess
import sys


OPSCTL = "/usr/local/bin/opsctl"
APP_DIR = "/opt/mc-robot-shop"
ZERO_ARG_COMMANDS = {"targets", "help", "-h", "--help"}
SAFE_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
ALLOWED_ENV_KEYS = {"MC_ROBOT_CLOUD", "MC_ROBOT_APP_DIR", "MC_ALIYUN_HOST", "MC_TENCENT_HOST"}


def deny(message="command not allowed"):
    print(message, file=sys.stderr)
    raise SystemExit(126)


def parse_request():
    original = os.environ.get("SSH_ORIGINAL_COMMAND", "").strip()
    if not original:
        deny("interactive shell is disabled")
    if "\n" in original or "\r" in original or "\x00" in original:
        deny("invalid command characters")
    try:
        tokens = shlex.split(original, posix=True)
    except ValueError:
        deny("command parse failed")
    env = {}
    while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
        key, value = tokens.pop(0).split("=", 1)
        if key not in ALLOWED_ENV_KEYS:
            deny("environment override not allowed")
        if key in {"MC_ALIYUN_HOST", "MC_TENCENT_HOST"} and not SAFE_HOST.fullmatch(value):
            deny("target host override is invalid")
        env[key] = value
    if not tokens or tokens[0] not in {"opsctl", OPSCTL}:
        deny("only opsctl is allowed")
    return env, tokens[1:]


def validate_args(args):
    if not args:
        return ["help"]
    if len(args) > 64 or any(len(item) > 2000 for item in args):
        deny("command is too large")
    command, rest = args[0], args[1:]
    if command in ZERO_ARG_COMMANDS:
        if rest:
            deny("unexpected arguments")
        return args
    if command != "run" or not rest:
        deny("unknown opsctl command")
    if rest[0] not in {
        "uptime",
        "free",
        "curl",
        "df",
        "find",
        "lsof",
        "cat",
        "vmstat",
        "iostat",
        "ip",
        "ss",
        "sysctl",
        "iptables",
        "tc",
        "ps",
        "docker",
        "redis-cli",
        "rabbitmqctl",
        "mysql",
        "mongosh",
        "openssl",
        "tracepath",
        "ping",
        "date",
    }:
        deny("command is not in the read-only allowlist")
    return args


def main():
    env_overrides, requested_args = parse_request()
    cloud = env_overrides.get("MC_ROBOT_CLOUD", "").strip().lower()
    if cloud not in {"aliyun", "tencent"}:
        deny("cloud must be aliyun or tencent")
    if env_overrides.get("MC_ROBOT_APP_DIR", APP_DIR) != APP_DIR:
        deny("application directory override not allowed")
    clean_env = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "MC_ROBOT_CLOUD": cloud,
        "MC_ROBOT_APP_DIR": APP_DIR,
        "MC_ALIYUN_HOST": env_overrides.get("MC_ALIYUN_HOST", ""),
        "MC_TENCENT_HOST": env_overrides.get("MC_TENCENT_HOST", ""),
    }
    completed = subprocess.run(
        ["sudo", "-n", OPSCTL, *validate_args(requested_args)],
        env=clean_env,
        text=True,
        timeout=60,
        check=False,
    )
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
