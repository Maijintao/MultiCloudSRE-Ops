#!/usr/bin/env python3
"""Basic read-only ops observations over SSH for production-style Robot Shop cases."""

import os
import re
import shlex
import subprocess
from typing import Optional

from mcp.server.fastmcp import FastMCP


SERVER = FastMCP(
    "multi-cloud-ssh",
    instructions=(
        "Restricted read-only SSH observations for the contest environment. "
        "Tools execute approved commands on the selected target and do not provide arbitrary shell access, "
        "case labels, diagnosis hints, or conclusions."
    ),
    log_level="ERROR",
)

CLOUDS = {
    "aliyun": {
        "host": os.environ.get("MC_ALIYUN_HOST", "203.0.113.10"),
        "user": os.environ.get("OJ_MULTI_CLOUD_MCP_ALIYUN_USER") or os.environ.get("MC_ALIYUN_USER", "ojobserver"),
        "port": os.environ.get("MC_ALIYUN_PORT", "22"),
    },
    "tencent": {
        "host": os.environ.get("MC_TENCENT_HOST", "198.51.100.10"),
        "user": os.environ.get("OJ_MULTI_CLOUD_MCP_TENCENT_USER") or os.environ.get("MC_TENCENT_USER", "ojobserver"),
        "port": os.environ.get("MC_TENCENT_PORT", "22"),
    },
}
APP_DIR = os.environ.get("MC_ROBOT_APP_DIR", "/opt/mc-robot-shop")
SSH_KEY = (
    os.environ.get("MC_SSH_IDENTITY_FILE")
    or os.environ.get("OJ_SSH_IDENTITY_FILE")
    or os.environ.get("FAULT_TARGET_IDENTITY_FILE")
    or ""
)
MAX_OUTPUT_CHARS = int(os.environ.get("OJ_MULTI_CLOUD_MCP_MAX_OUTPUT_CHARS", "60000"))
SAFE_SERVICE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SAFE_PATH = re.compile(r"^/[A-Za-z0-9_./?=&%:+,-]{0,400}$")
READONLY_COMMANDS = {
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
}

LEAK_PATTERNS = [
    r"mc_origin_conntrack_cdn_smoke",
    r"mc_tencent_egress_degrade",
    r"mc_api_schema_rum_js_error",
    r"mc_redis_hotkey_eviction",
    r"mc_rabbitmq_backlog_order_lag",
    r"mc_cdn_static_host_403",
    r"mc_trace_context_break",
    r"mc_clock_skew_signature",
    r"ops_frontend_render_anomaly",
    r"ops_network_health_audit",
    r"ops_io_writeback_stall",
    r"ops_file_capacity_audit",
    r"ops_connection_pool_anomaly",
    r"ops_read_after_write_gap",
    r"ops_redis_latency_audit",
    r"ops_cpu_efficiency_audit",
    r"ops_waf_regex_cpu_burn",
    r"ops_clb_host_healthcheck_misroute",
    r"ops_frontend_payload_longtask",
    r"ops_jvm_gc_pause_shipping",
    r"ops_syn_backlog_overflow",
    r"ops_mysql_metadata_lock_checkout",
    r"ops_mongodb_missing_index_catalogue",
    r"ops_rabbitmq_ttl_deadletter_drop",
    r"ops_tls_handshake_session_cache",
    r"ops_mtu_blackhole_large_payload",
    r"ops_composite_polling_timeout_cpuset",
    r"ops_composite_checkout_rowlock_retry_memory",
    r"ops_composite_cart_bigkey_pid_leak",
    r"ops_composite_gateway_limits_txqueue",
    r"ops_composite_data_plane_profile_alarm_io",
    r"ops_composite_observability_cardinality_pressure",
    r"ops_composite_batch_tmpdisk_openfile_zombie",
    r"ops_composite_traffic_skew_db_cpu_pressure",
    r"搜索高峰期入口卡慢",
    r"全局入口健康巡检",
    r"商品页交互卡顿",
    r"运费报价周期性卡顿",
    r"高峰期连接建立失败",
    r"结算请求偶发挂起",
    r"商品检索慢查询巡检",
    r"订单事件偶发丢失",
    r"首屏建连耗时异常",
    r"大请求跨云超时",
    r"大促前全栈容量巡检",
    r"结算链路综合巡检",
    r"购物车服务综合巡检",
    r"双云入口可靠性巡检",
    r"数据平面综合巡检",
    r"可观测性开销巡检",
    r"夜间批处理后资源巡检",
    r"跨云流量与容量巡检",
    r"catastrophic\s+backtracking",
    r"healthcheck[-_\s]*misroute",
    r"payload[-_\s]*longtask",
    r"gc[-_\s]*pause[-_\s]*shipping",
    r"syn[-_\s]*backlog[-_\s]*overflow",
    r"metadata[-_\s]*lock[-_\s]*checkout",
    r"missing[-_\s]*index[-_\s]*catalogue",
    r"ttl[-_\s]*deadletter[-_\s]*drop",
    r"session[-_\s]*cache[-_\s]*(?:root[-_\s]*cause|failure)",
    r"mtu[-_\s]*blackhole",
    r"host_mismatch",
    r"pmtu\s+anomaly\s+observed",
    r"indexHint",
    r"missing\s+category_1_price_1",
    r"accept\s+queue\s+is\s+full",
    r"blackhole_after_bytes",
    r"mss_clamp",
    r"fault_active",
    r"root\s*cause",
    r"inject(?:ion)?",
    r"recover(?:y)?",
    r"state/[^\\s]+\\.json",
    r"conntrack-saturation",
    r"netem-summary",
    r"rum-summary",
    r"redis-summary",
    r"mq-summary",
    r"cdn-summary",
    r"trace-summary",
    r"time-summary",
    r"schema-bad",
    r"clock-skew",
    r"trace-break",
]


def redact(text: str) -> str:
    output = str(text or "")
    for pattern in LEAK_PATTERNS:
        output = re.sub(pattern, "[redacted]", output, flags=re.IGNORECASE)
    return output


def checked_cloud(cloud: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    value = str(cloud or "aliyun").strip().lower()
    aliases = {"ali": "aliyun", "alibaba": "aliyun", "tx": "tencent", "tencentcloud": "tencent"}
    value = aliases.get(value, value)
    if value not in CLOUDS:
        return None, 'cloud must be "aliyun" or "tencent"'
    return value, None


def checked_path(path: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    value = str(path or "/").strip()
    if not value.startswith("/"):
        value = "/" + value
    if not SAFE_PATH.fullmatch(value):
        return None, "path contains unsupported characters"
    return value, None


def checked_name(value: Optional[str], pattern: re.Pattern, label: str) -> tuple[Optional[str], Optional[str]]:
    text = str(value or "").strip()
    if not pattern.fullmatch(text):
        return None, f"{label} contains unsupported characters"
    return text, None


def checked_count(count: int) -> int:
    try:
        number = int(count)
    except Exception:
        number = 8
    return max(1, min(number, 30))


def checked_command(command: Optional[str]) -> tuple[Optional[list[str]], Optional[str]]:
    text = str(command or "").strip()
    if not text:
        return None, "command is required"
    if any(character in text for character in ("\x00", "\r", "\n")):
        return None, "command contains unsupported control characters"
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        return None, "command parse failed"
    if not tokens:
        return None, "command is required"
    if tokens[0] == "run":
        tokens = tokens[1:]
        if not tokens:
            return None, "command is required after run"
    if tokens[0] == "sudo":
        tokens = tokens[1:]
        if not tokens:
            return None, "command is required after sudo"
    if len(tokens) > 64 or any(len(token) > 2000 for token in tokens):
        return None, "command has too many arguments"
    if tokens[0] not in READONLY_COMMANDS and tokens[0] not in {"help", "-h", "--help"}:
        return None, "command is not in the read-only allowlist"
    if any(
        token in {"|", ";", "&&", "||", "`", "&", ">", ">>", "<"}
        or "|" in token
        or ";" in token
        or "`" in token
        or token.startswith((">", ">>", "2>", "1>", "<"))
        for token in tokens
    ):
        return None, "shell operators are not supported"
    return tokens, None


def normalize_readonly_tokens(tokens: list[str]) -> list[str]:
    if len(tokens) == 2 and tokens[0] == "ss" and tokens[1].startswith("-"):
        flags = set(tokens[1][1:])
        if {"l", "t", "n"}.issubset(flags) and flags.issubset({"l", "t", "n", "p"}):
            return ["ss", "-ltn"]
    return tokens


def run_ssh(cloud: str, remote_command: str) -> str:
    if not SSH_KEY or not os.path.exists(SSH_KEY):
        return (
            "multi-cloud-ssh MCP is configured, but the SSH identity file is not available."
        )
    target = CLOUDS[cloud]
    ssh_cmd = [
        "ssh",
        "-i",
        SSH_KEY,
        "-p",
        target["port"],
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "UserKnownHostsFile=/tmp/oj_multi_cloud_known_hosts",
        "-o",
        "ConnectTimeout=10",
        f"{target['user']}@{target['host']}",
        remote_command,
    ]
    try:
        completed = subprocess.run(
            ssh_cmd,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return "remote opsctl request timed out after 45 seconds"
    except OSError as exc:
        return f"ssh unavailable: {exc}"
    output = (completed.stdout or "") + (completed.stderr or "")
    if not output:
        output = f"ssh exited with status {completed.returncode}"
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n...[truncated]"
    return redact(output)


def run_opsctl(cloud: Optional[str], args: list[str]) -> str:
    checked, error = checked_cloud(cloud)
    if error:
        return error
    quoted_args = " ".join(shlex.quote(item) for item in args)
    command = (
        f"MC_ROBOT_CLOUD={shlex.quote(checked)} "
        f"MC_ROBOT_APP_DIR={shlex.quote(APP_DIR)} "
        f"MC_ALIYUN_HOST={shlex.quote(CLOUDS['aliyun']['host'])} "
        f"MC_TENCENT_HOST={shlex.quote(CLOUDS['tencent']['host'])} "
        f"opsctl {quoted_args}"
    )
    return run_ssh(checked, command)


@SERVER.tool(description="List configured targets and entry URLs.")
def targets() -> str:
    rows = []
    for name, data in CLOUDS.items():
        entry = f"http://{data['host']}:18081/"
        if name == "aliyun":
            entry += f" global=http://{data['host']}:18080/"
        rows.append(f"{name} {entry}")
    return "\n".join(rows)


@SERVER.tool(
    description=(
        "Run one approved real read-only command on a configured target over SSH. "
        "Use command='help' to list the generic command forms; shell operators and writes are unavailable."
    )
)
def run(cloud: Optional[str] = None, command: Optional[str] = None) -> str:
    tokens, error = checked_command(command)
    if error:
        return error
    if tokens[0] in {"help", "-h", "--help"}:
        return run_opsctl(cloud, ["help"])
    tokens = normalize_readonly_tokens(tokens)
    if tokens == ["docker", "logs"]:
        return "docker logs requires one service name; use docker ps to list service names"
    output = run_opsctl(cloud, ["run", *tokens])
    if "unsupported read-only command" in output:
        output += "\nUse command='help' to list approved read-only forms."
    return output


if __name__ == "__main__":
    SERVER.run(transport="stdio")
