#!/usr/bin/env python3
"""Restricted kubectl-backed MCP server for contestant diagnostics."""

import os
import re
import subprocess
from typing import Optional

from mcp.server.fastmcp import FastMCP


SERVER = FastMCP(
    "k3s-cluster",
    instructions="Read-only Kubernetes inspection for the contest namespace across the provided clusters.",
    log_level="ERROR",
)
KUBECTL = os.environ.get("OJ_K3S_KUBECTL", "/usr/local/bin/kubectl")
ALLOWED_CONTEXTS = {
    item.strip()
    for item in os.environ.get("OJ_K3S_ALLOWED_CONTEXTS", "alicloud,tencent,aws").split(",")
    if item.strip()
}
ALLOWED_NAMESPACE = os.environ.get("OJ_K3S_NAMESPACE", "seat-1").strip() or "seat-1"
MAX_OUTPUT_CHARS = int(os.environ.get("OJ_K3S_MAX_OUTPUT_CHARS", "60000"))
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,252}$")
KINDS = {
    "pod": "pods",
    "pods": "pods",
    "deployment": "deployments",
    "deployments": "deployments",
    "deploy": "deployments",
    "service": "services",
    "services": "services",
    "svc": "services",
    "configmap": "configmaps",
    "configmaps": "configmaps",
    "cm": "configmaps",
    "event": "events",
    "events": "events",
    "replicaset": "replicasets",
    "replicasets": "replicasets",
    "rs": "replicasets",
    "statefulset": "statefulsets",
    "statefulsets": "statefulsets",
    "sts": "statefulsets",
    "daemonset": "daemonsets",
    "daemonsets": "daemonsets",
    "ds": "daemonsets",
    "ingress": "ingress",
    "ingresses": "ingress",
    "pvc": "persistentvolumeclaims",
    "persistentvolumeclaim": "persistentvolumeclaims",
    "persistentvolumeclaims": "persistentvolumeclaims",
    "endpoint": "endpoints",
    "endpoints": "endpoints",
    "iochaos": "iochaos",
    "networkchaos": "networkchaos",
    "dnschaos": "dnschaos",
    "stresschaos": "stresschaos",
    "podchaos": "podchaos",
}


def _contexts_text() -> str:
    return ", ".join(sorted(ALLOWED_CONTEXTS))


def context_hint(context: Optional[str]) -> str:
    value = str(context or "").strip() or "（空）"
    return f'当前只开放以下 context: {_contexts_text()}。你传入的 "{value}" 不可用，请改用 context="alicloud"、"tencent" 或 "aws"。'


def namespace_hint(namespace: Optional[str]) -> str:
    value = str(namespace or "").strip() or "（空）"
    if value in ALLOWED_CONTEXTS or value == "aliyun":
        return (
            f'当前考试环境只开放 {ALLOWED_NAMESPACE} 命名空间。你传入的 "{value}" 像是 context，不是 namespace。'
            f' 请用 namespace="{ALLOWED_NAMESPACE}"，并把云厂商放到 context 参数里。'
        )
    return f'当前考试环境只开放 {ALLOWED_NAMESPACE} 命名空间。你传入的 "{value}" 不可用。请用 namespace="{ALLOWED_NAMESPACE}" 重试。'


def kind_hint(kind: Optional[str]) -> str:
    value = str(kind or "").strip()
    if not value:
        return (
            "请指定资源类型 kind 参数。例如: pods, deployments, services, events, configmaps, "
            "stresschaos, networkchaos, iochaos, podchaos, dnschaos 等。"
        )
    return (
        f'暂不支持 kind="{value}"。可用 kind 包括: '
        "pods, deployments, services, configmaps, events, replicasets, statefulsets, daemonsets, "
        "ingress, persistentvolumeclaims, endpoints, iochaos, networkchaos, dnschaos, stresschaos, podchaos。"
    )


def name_hint(kind: Optional[str], field: str) -> str:
    label = str(kind or "").strip() or "资源"
    if field == "pod name":
        return '请指定 pod 名称参数。例如: pod="checkoutservice-xxx"。'
    return f'请指定资源名称 name 参数。如果要列出所有 {label}，请用 list_resources 工具，kind="{label}"。'


def checked_context(context: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    value = (context or "alicloud").strip()
    if value not in ALLOWED_CONTEXTS:
        return None, context_hint(value)
    return value, None


def checked_namespace(namespace: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    value = (namespace or ALLOWED_NAMESPACE).strip()
    if value != ALLOWED_NAMESPACE:
        return None, namespace_hint(value)
    return value, None


def checked_kind(kind: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    value = KINDS.get(str(kind or "").strip().lower())
    if not value:
        return None, kind_hint(kind)
    return value, None


def checked_name(value: Optional[str], field: str, kind: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    text = str(value or "").strip()
    if not text:
        return None, name_hint(kind, field)
    if not SAFE_NAME.fullmatch(text):
        return None, f"{field} 格式不合法，请只使用字母、数字、点、下划线或连字符。"
    return text, None


def run_kubectl(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            [KUBECTL, *args],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return "kubectl request timed out after 30 seconds"
    except OSError as exc:
        return f"kubectl unavailable: {exc}"
    output = (completed.stdout or "") + (completed.stderr or "")
    if not output:
        output = f"kubectl exited with status {completed.returncode}"
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n...[truncated]"
    return output


def namespaced_args(context: Optional[str], namespace: Optional[str]) -> tuple[Optional[list[str]], Optional[str]]:
    checked_ctx, ctx_error = checked_context(context)
    if ctx_error:
        return None, ctx_error
    checked_ns, ns_error = checked_namespace(namespace)
    if ns_error:
        return None, ns_error
    return ["--context", checked_ctx, "-n", checked_ns], None


@SERVER.tool(description="List approved Kubernetes resources in the contest namespace.")
def list_resources(
    kind: Optional[str] = None,
    namespace: Optional[str] = None,
    context: Optional[str] = None,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
) -> str:
    base_args, error = namespaced_args(context, namespace)
    if error:
        return error
    checked_resource, error = checked_kind(kind)
    if error:
        return error
    args = [*base_args, "get", checked_resource, "-o", "wide"]
    if label_selector:
        args.extend(["-l", str(label_selector)])
    if field_selector:
        args.extend(["--field-selector", str(field_selector)])
    return run_kubectl(args)


@SERVER.tool(description="Get YAML for an approved Kubernetes resource in the contest namespace.")
def get_resource(kind: Optional[str] = None, name: Optional[str] = None, namespace: Optional[str] = None, context: Optional[str] = None) -> str:
    base_args, error = namespaced_args(context, namespace)
    if error:
        return error
    checked_resource, error = checked_kind(kind)
    if error:
        return error
    checked_resource_name, error = checked_name(name, "resource name", checked_resource)
    if error:
        return error
    return run_kubectl(
        [
            *base_args,
            "get",
            checked_resource,
            checked_resource_name,
            "-o",
            "yaml",
        ]
    )


@SERVER.tool(description="Describe an approved Kubernetes resource and its observed events.")
def describe_resource(kind: Optional[str] = None, name: Optional[str] = None, namespace: Optional[str] = None, context: Optional[str] = None) -> str:
    base_args, error = namespaced_args(context, namespace)
    if error:
        return error
    checked_resource, error = checked_kind(kind)
    if error:
        return error
    checked_resource_name, error = checked_name(name, "resource name", checked_resource)
    if error:
        return error
    return run_kubectl(
        [
            *base_args,
            "describe",
            checked_resource,
            checked_resource_name,
        ]
    )


@SERVER.tool(description="Read recent logs from a pod in the contest namespace.")
def get_logs(
    pod: Optional[str] = None,
    namespace: Optional[str] = None,
    context: Optional[str] = None,
    container: Optional[str] = None,
    tail_lines: int = 100,
    previous: bool = False,
) -> str:
    base_args, error = namespaced_args(context, namespace)
    if error:
        return error
    checked_pod, error = checked_name(pod, "pod name")
    if error:
        return error
    tail = max(1, min(int(tail_lines), 500))
    args = [
        *base_args,
        "logs",
        checked_pod,
        f"--tail={tail}",
    ]
    if container:
        checked_container, error = checked_name(container, "container name")
        if error:
            return error
        args.extend(["-c", checked_container])
    if previous:
        args.append("--previous")
    return run_kubectl(args)


@SERVER.tool(description="List recent events from the contest namespace.")
def get_events(namespace: Optional[str] = None, context: Optional[str] = None, field_selector: Optional[str] = None) -> str:
    base_args, error = namespaced_args(context, namespace)
    if error:
        return error
    args = [*base_args, "get", "events", "--sort-by=.lastTimestamp"]
    if field_selector:
        args.extend(["--field-selector", str(field_selector)])
    return run_kubectl(args)


@SERVER.tool(description="List the three provided cluster contexts.")
def list_contexts() -> str:
    return "\n".join(sorted(ALLOWED_CONTEXTS)) + "\n"


@SERVER.tool(description="Show resource usage for pods in the contest namespace, when metrics are available.")
def top_pods(namespace: Optional[str] = None, context: Optional[str] = None) -> str:
    base_args, error = namespaced_args(context, namespace)
    if error:
        return error
    return run_kubectl([*base_args, "top", "pods"])


@SERVER.tool(description="List the common workload and service resources in the contest namespace.")
def get_all(namespace: Optional[str] = None, context: Optional[str] = None) -> str:
    base_args, error = namespaced_args(context, namespace)
    if error:
        return error
    return run_kubectl([*base_args, "get", "all", "-o", "wide"])


if __name__ == "__main__":
    SERVER.run(transport="stdio")
