import json
import os
import shlex
from pathlib import Path


ALIBABA_MCP_SERVER_NAME = "alibaba-cloud-ops-mcp-server"
K3S_MCP_SERVER_NAME = "k3s-cluster"
RUM_MCP_SERVER_NAME = "rum"
RUM2_MCP_SERVER_NAME = "rum2"
MULTI_CLOUD_SSH_MCP_SERVER_NAME = "multi-cloud-ssh"
ANSWER_MCP_SNAPSHOT_COLUMN = "answer_mcp_servers_json"
DEFAULT_CASE_MCP_SERVERS = [
    ALIBABA_MCP_SERVER_NAME,
    K3S_MCP_SERVER_NAME,
    RUM_MCP_SERVER_NAME,
    RUM2_MCP_SERVER_NAME,
    MULTI_CLOUD_SSH_MCP_SERVER_NAME,
]
AVAILABLE_CASE_MCP_SERVERS = list(DEFAULT_CASE_MCP_SERVERS)
PUBLIC_CASE_MCP_SERVER_LABELS = {
    ALIBABA_MCP_SERVER_NAME: "Alibaba Cloud Ops",
    K3S_MCP_SERVER_NAME: "K3s Cluster",
    RUM_MCP_SERVER_NAME: "Tencent RUM",
    RUM2_MCP_SERVER_NAME: "Tencent RUM #2",
    MULTI_CLOUD_SSH_MCP_SERVER_NAME: "Multi-Cloud SSH",
}
ORDERED_MCP_SERVER_NAMES = [
    ALIBABA_MCP_SERVER_NAME,
    K3S_MCP_SERVER_NAME,
    RUM_MCP_SERVER_NAME,
    RUM2_MCP_SERVER_NAME,
    MULTI_CLOUD_SSH_MCP_SERVER_NAME,
]
MCP_SERVER_NAMES = set(ORDERED_MCP_SERVER_NAMES)


def alibaba_mcp_config():
    env = {
        "UV_PYTHON": os.environ.get("OJ_MCP_UV_PYTHON", os.environ.get("UV_PYTHON", "3.12")),
        "ALIBABA_CLOUD_ACCESS_KEY_ID": os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", ""),
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", ""),
        "ALIBABA_CLOUD_REGION_ID": os.environ.get("ALIBABA_CLOUD_REGION_ID", "cn-guangzhou"),
    }
    return {
        ALIBABA_MCP_SERVER_NAME: {
            "timeout": int(os.environ.get("OJ_MCP_TIMEOUT", "600")),
            "connect_timeout": int(os.environ.get("OJ_MCP_CONNECT_TIMEOUT", "240")),
            "command": os.environ.get("OJ_MCP_COMMAND", "uvx"),
            "args": [item for item in os.environ.get("OJ_MCP_ARGS", "alibaba-cloud-ops-mcp-server@latest").split() if item],
            "env": env,
        }
    }


def k3s_mcp_config():
    container_runtime_dir = os.environ.get("OJ_K3S_MCP_CONTAINER_RUNTIME_DIR", "/opt/oj-k3s-mcp-runtime").strip()
    return {
        K3S_MCP_SERVER_NAME: {
            "timeout": int(os.environ.get("OJ_K3S_MCP_TIMEOUT", "600")),
            "connect_timeout": int(os.environ.get("OJ_K3S_MCP_CONNECT_TIMEOUT", "240")),
            "command": os.environ.get("OJ_K3S_MCP_COMMAND", "/opt/hermes-agent/venv/bin/python"),
            "args": shlex.split(
                os.environ.get(
                    "OJ_K3S_MCP_ARGS",
                    f"{container_runtime_dir}/k8s_readonly_mcp.py",
                )
            ),
            "env": {
                "KUBECONFIG": os.environ.get(
                    "OJ_K3S_MCP_CONTAINER_KUBECONFIG",
                    "/home/hermes/.kube/config-readonly.yaml",
                ),
                "OJ_K3S_KUBECTL": os.environ.get("OJ_K3S_CONTAINER_KUBECTL_PATH", "/usr/local/bin/kubectl"),
                "OJ_K3S_ALLOWED_CONTEXTS": os.environ.get(
                    "OJ_K3S_ALLOWED_CONTEXTS",
                    "server1,server2,server3,alicloud,tencent,aws",
                ),
                "OJ_K3S_NAMESPACE": os.environ.get("OJ_K3S_NAMESPACE", "seat-1"),
            },
        }
    }


def rum_mcp_env_keys(server_name):
    if server_name == RUM2_MCP_SERVER_NAME:
        return {
            "url": "OJ_RUM2_MCP_URL",
            "secret_id": "OJ_RUM2_MCP_SECRET_ID",
            "secret_key": "OJ_RUM2_MCP_SECRET_KEY",
            "timeout": "OJ_RUM2_MCP_TIMEOUT",
            "connect_timeout": "OJ_RUM2_MCP_CONNECT_TIMEOUT",
        }
    return {
        "url": "OJ_RUM_MCP_URL",
        "secret_id": "OJ_RUM_MCP_SECRET_ID",
        "secret_key": "OJ_RUM_MCP_SECRET_KEY",
        "timeout": "OJ_RUM_MCP_TIMEOUT",
        "connect_timeout": "OJ_RUM_MCP_CONNECT_TIMEOUT",
    }


def rum_mcp_config(server_name=RUM_MCP_SERVER_NAME):
    env_keys = rum_mcp_env_keys(server_name)
    return {
        server_name: {
            "timeout": int(os.environ.get(env_keys["timeout"], "600")),
            "connect_timeout": int(os.environ.get(env_keys["connect_timeout"], "120")),
            "url": os.environ.get(env_keys["url"], "https://app.rumt-zh.com/sse").strip(),
            "headers": {
                "SecretId": "${" + env_keys["secret_id"] + "}",
                "SecretKey": "${" + env_keys["secret_key"] + "}",
            },
        }
    }


def multi_cloud_ssh_mcp_config():
    default_runtime_dir = Path(__file__).resolve().parents[1] / "runtime" / "multi-cloud-ssh-mcp"
    container_runtime_dir = os.environ.get(
        "OJ_MULTI_CLOUD_MCP_CONTAINER_RUNTIME_DIR",
        "/opt/oj-multi-cloud-ssh-mcp",
    ).strip()
    aliyun_user = os.environ.get(
        "OJ_MULTI_CLOUD_MCP_ALIYUN_USER",
        os.environ.get("MC_ALIYUN_USER", "ojobserver"),
    )
    tencent_user = os.environ.get(
        "OJ_MULTI_CLOUD_MCP_TENCENT_USER",
        os.environ.get("MC_TENCENT_USER", "ojobserver"),
    )
    default_identity = (
        "/run/secrets/oj_ssh_key"
        if os.environ.get("OJ_HERMES_DOCKER", "1") != "0"
        else os.environ.get("OJ_MULTI_CLOUD_MCP_IDENTITY_FILE", "/root/.ssh/oj_observer_key")
    )
    return {
        MULTI_CLOUD_SSH_MCP_SERVER_NAME: {
            "timeout": int(os.environ.get("OJ_MULTI_CLOUD_MCP_TIMEOUT", "600")),
            "connect_timeout": int(os.environ.get("OJ_MULTI_CLOUD_MCP_CONNECT_TIMEOUT", "120")),
            "command": os.environ.get("OJ_MULTI_CLOUD_MCP_COMMAND", "/opt/hermes-agent/venv/bin/python"),
            "args": shlex.split(
                os.environ.get(
                    "OJ_MULTI_CLOUD_MCP_ARGS",
                    f"{container_runtime_dir}/multi_cloud_ssh_mcp.py",
                )
            ),
            "env": {
                "MC_ALIYUN_HOST": os.environ.get("MC_ALIYUN_HOST", "203.0.113.10"),
                "MC_ALIYUN_USER": aliyun_user,
                "OJ_MULTI_CLOUD_MCP_ALIYUN_USER": aliyun_user,
                "MC_ALIYUN_PORT": os.environ.get("MC_ALIYUN_PORT", "22"),
                "MC_TENCENT_HOST": os.environ.get("MC_TENCENT_HOST", "198.51.100.10"),
                "MC_TENCENT_USER": tencent_user,
                "OJ_MULTI_CLOUD_MCP_TENCENT_USER": tencent_user,
                "MC_TENCENT_PORT": os.environ.get("MC_TENCENT_PORT", "22"),
                "MC_ROBOT_APP_DIR": os.environ.get("MC_ROBOT_APP_DIR", "/opt/mc-robot-shop"),
                "MC_SSH_IDENTITY_FILE": os.environ.get("OJ_MULTI_CLOUD_MCP_IDENTITY_FILE", default_identity),
                "OJ_MULTI_CLOUD_MCP_RUNTIME_DIR": os.environ.get(
                    "OJ_MULTI_CLOUD_MCP_RUNTIME_DIR",
                    str(default_runtime_dir),
                ),
                "OJ_MULTI_CLOUD_MCP_MAX_OUTPUT_CHARS": os.environ.get(
                    "OJ_MULTI_CLOUD_MCP_MAX_OUTPUT_CHARS",
                    "60000",
                ),
            },
        }
    }

def selected_mcp_config(toolset_list):
    toolsets = set(toolset_list or [])
    config = {}
    if ALIBABA_MCP_SERVER_NAME in toolsets:
        config.update(alibaba_mcp_config())
    if K3S_MCP_SERVER_NAME in toolsets:
        config.update(k3s_mcp_config())
    if RUM_MCP_SERVER_NAME in toolsets:
        config.update(rum_mcp_config(RUM_MCP_SERVER_NAME))
    if RUM2_MCP_SERVER_NAME in toolsets:
        config.update(rum_mcp_config(RUM2_MCP_SERVER_NAME))
    if MULTI_CLOUD_SSH_MCP_SERVER_NAME in toolsets:
        config.update(multi_cloud_ssh_mcp_config())
    return config


def default_case_mcp_servers():
    return list(DEFAULT_CASE_MCP_SERVERS)


def public_case_mcp_server_options():
    return [
        {
            "id": server_name,
            "label": PUBLIC_CASE_MCP_SERVER_LABELS.get(server_name, server_name),
        }
        for server_name in AVAILABLE_CASE_MCP_SERVERS
    ]


def public_case_mcp_server_label(server_name):
    return PUBLIC_CASE_MCP_SERVER_LABELS.get(server_name, server_name)


def normalize_selected_public_mcp_servers(value, default_to_all=True):
    if value is None:
        return default_case_mcp_servers() if default_to_all else []
    if not isinstance(value, list):
        raise ValueError("mcp_servers must be a list")
    allowed = set(AVAILABLE_CASE_MCP_SERVERS)
    selected = []
    for server in value:
        name = str(server or "").strip()
        if not name:
            continue
        if name not in allowed:
            raise ValueError(f"unsupported submission mcp server: {name}")
        if name not in selected:
            selected.append(name)
    return selected


def dump_answer_mcp_servers_json(servers):
    return json.dumps(normalize_selected_public_mcp_servers(servers), ensure_ascii=False)


def parse_answer_mcp_servers_json(raw):
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("submission mcp snapshot is invalid JSON") from exc
    return normalize_selected_public_mcp_servers(value)


def answer_mcp_servers(case=None, submission=None):
    if submission:
        snapshot = parse_answer_mcp_servers_json(submission.get(ANSWER_MCP_SNAPSHOT_COLUMN))
        if snapshot is not None:
            return snapshot
    if case and "mcp_servers" in case:
        return normalize_selected_public_mcp_servers(case.get("mcp_servers"), default_to_all=False)
    return default_case_mcp_servers()


def mcp_configured(server_name=ALIBABA_MCP_SERVER_NAME):
    if server_name == K3S_MCP_SERVER_NAME:
        path = os.environ.get("OJ_K3S_READONLY_KUBECONFIG", "").strip()
        return bool(path and os.path.isfile(path))
    if server_name in {RUM_MCP_SERVER_NAME, RUM2_MCP_SERVER_NAME}:
        env_keys = rum_mcp_env_keys(server_name)
        return all(
            os.environ.get(key)
            for key in (
                env_keys["url"],
                env_keys["secret_id"],
                env_keys["secret_key"],
            )
        )
    if server_name == MULTI_CLOUD_SSH_MCP_SERVER_NAME:
        if os.environ.get("OJ_MULTI_CLOUD_MCP_ENABLED", "").strip().lower() in {"1", "true", "yes"}:
            return True
        runtime_dir = os.environ.get("OJ_MULTI_CLOUD_MCP_RUNTIME_DIR", "").strip()
        if runtime_dir:
            return Path(runtime_dir).exists()
        default_runtime_dir = Path(__file__).resolve().parents[1] / "runtime" / "multi-cloud-ssh-mcp"
        return default_runtime_dir.exists()
    return all(
        os.environ.get(key)
        for key in (
            "ALIBABA_CLOUD_ACCESS_KEY_ID",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
            "ALIBABA_CLOUD_REGION_ID",
        )
    )
