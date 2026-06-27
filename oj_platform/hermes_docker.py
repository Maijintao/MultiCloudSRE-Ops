import os
import shutil
import subprocess
import uuid
from pathlib import Path

from . import settings
from .hermes_setup import host_ssh_identity
from .mcp import (
    ALIBABA_MCP_SERVER_NAME,
    K3S_MCP_SERVER_NAME,
    MULTI_CLOUD_SSH_MCP_SERVER_NAME,
    RUM_MCP_SERVER_NAME,
    RUM2_MCP_SERVER_NAME,
    mcp_configured,
)


def docker_mount(source, target, readonly=False):
    value = f"type=bind,source={source},target={target}"
    if readonly:
        value += ",readonly"
    return value


def hermes_python_mounts():
    mounts = []
    venv_python = Path(settings.HERMES_LIB) / "venv" / "bin" / "python"
    try:
        if not venv_python.is_symlink():
            return mounts
        target = os.readlink(venv_python)
        if not target.startswith("/"):
            return mounts
        target_path = Path(target)
        if target_path.parent.name == "bin" and len(target_path.parents) >= 3:
            runtime_root = target_path.parents[2]
        else:
            runtime_root = target_path.parent
        if runtime_root.exists():
            mounts.append((runtime_root, runtime_root))
    except OSError:
        pass
    return mounts


def mcp_runtime_mounts(phase, toolsets):
    if phase != "answer":
        return []
    selected = set(str(toolsets or "").split(","))
    runtime_dir = os.environ.get("OJ_MCP_RUNTIME_DIR", "").strip()
    container_runtime_dir = os.environ.get("OJ_MCP_CONTAINER_RUNTIME_DIR", "/opt/oj-mcp-runtime").strip()
    mounts = []
    if ALIBABA_MCP_SERVER_NAME in selected:
        if runtime_dir and container_runtime_dir and Path(runtime_dir).exists():
            mounts.append((runtime_dir, container_runtime_dir))
        if os.environ.get("OJ_MCP_COMMAND", "uvx") == "uvx":
            search_path = "/root/.local/bin:/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", "")
            for binary in ("uv", "uvx"):
                source = shutil.which(binary, path=search_path)
                if source:
                    mounts.append((source, f"/usr/local/bin/{binary}"))
    if K3S_MCP_SERVER_NAME in selected:
        k3s_runtime_dir = os.environ.get("OJ_K3S_MCP_RUNTIME_DIR", "").strip()
        k3s_container_dir = os.environ.get("OJ_K3S_MCP_CONTAINER_RUNTIME_DIR", "/opt/oj-k3s-mcp-runtime").strip()
        if k3s_runtime_dir and k3s_container_dir and Path(k3s_runtime_dir).exists():
            mounts.append((k3s_runtime_dir, k3s_container_dir))
        kubectl_path = os.environ.get("OJ_K3S_KUBECTL_PATH", "/usr/local/bin/kubectl").strip()
        container_kubectl_path = os.environ.get("OJ_K3S_CONTAINER_KUBECTL_PATH", "/usr/local/bin/kubectl").strip()
        if kubectl_path and container_kubectl_path and Path(kubectl_path).exists():
            mounts.append((kubectl_path, container_kubectl_path))
        kubeconfig = os.environ.get("OJ_K3S_READONLY_KUBECONFIG", "").strip()
        if kubeconfig and Path(kubeconfig).exists():
            mounts.append((kubeconfig, "/home/hermes/.kube/config-readonly.yaml"))
    if MULTI_CLOUD_SSH_MCP_SERVER_NAME in selected:
        default_runtime_dir = Path(__file__).resolve().parents[1] / "runtime" / "multi-cloud-ssh-mcp"
        runtime_dir = os.environ.get("OJ_MULTI_CLOUD_MCP_RUNTIME_DIR", str(default_runtime_dir)).strip()
        container_dir = os.environ.get("OJ_MULTI_CLOUD_MCP_CONTAINER_RUNTIME_DIR", "/opt/oj-multi-cloud-ssh-mcp").strip()
        if runtime_dir and container_dir and Path(runtime_dir).exists():
            mounts.append((runtime_dir, container_dir))
    return mounts


def build_docker_command(home, workspace, runner_file, prompt_file, env_file, runtime_config, toolsets, skills):
    container_name = f"oj-hermes-{runtime_config['submission_id']}-{runtime_config['phase']}-{uuid.uuid4().hex[:8]}"
    cmd = ["docker", "run", "--rm", "--name", container_name, "--workdir", "/workspace"]
    if settings.HERMES_DOCKER_NETWORK:
        cmd.extend(["--network", settings.HERMES_DOCKER_NETWORK])
    if settings.HERMES_DOCKER_CPUS:
        cmd.extend(["--cpus", settings.HERMES_DOCKER_CPUS])
    if settings.HERMES_DOCKER_MEMORY:
        cmd.extend(["--memory", settings.HERMES_DOCKER_MEMORY])
    cmd.extend(["--security-opt", "no-new-privileges", "--env-file", str(env_file)])
    cmd.extend(["--mount", docker_mount(home, "/home/hermes")])
    cmd.extend(["--mount", docker_mount(workspace, "/workspace")])
    cmd.extend(["--mount", docker_mount(runner_file, "/runner/run_hermes_query.py", readonly=True)])
    cmd.extend(["--mount", docker_mount(prompt_file, "/runner/prompt.txt", readonly=True)])
    if Path(settings.HERMES_LIB).exists():
        cmd.extend(["--mount", docker_mount(settings.HERMES_LIB, settings.HERMES_CONTAINER_LIB, readonly=True)])
    for source, target in hermes_python_mounts():
        cmd.extend(["--mount", docker_mount(source, target, readonly=True)])
    for source, target in mcp_runtime_mounts(runtime_config["phase"], toolsets):
        cmd.extend(["--mount", docker_mount(source, target, readonly=True)])
    identity = host_ssh_identity()
    if identity and Path(identity).exists():
        cmd.extend(["--mount", docker_mount(identity, "/run/secrets/oj_ssh_key", readonly=True)])
    cmd.extend(settings.HERMES_DOCKER_EXTRA_ARGS)
    cmd.extend(
        [
            settings.HERMES_DOCKER_IMAGE,
            settings.HERMES_CONTAINER_PYTHON,
            "/runner/run_hermes_query.py",
            settings.HERMES_CONTAINER_LIB,
            "/runner/prompt.txt",
            "custom",
            runtime_config["model"],
            toolsets,
            skills,
            settings.AGENT_MAX_TURNS,
        ]
    )
    return cmd, container_name


def agent_status():
    docker_path = shutil.which("docker")
    hermes_path = shutil.which(settings.HERMES_BIN, path="/root/.local/bin:/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", ""))
    uvx_path = shutil.which("uvx", path="/root/.local/bin:/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", ""))
    status = {
        "runner": "docker" if settings.HERMES_DOCKER_ENABLED else "local",
        "docker_path": docker_path,
        "docker_image": settings.HERMES_DOCKER_IMAGE,
        "docker_network": settings.HERMES_DOCKER_NETWORK,
        "docker_available": bool(docker_path),
        "hermes_bin": settings.HERMES_BIN,
        "hermes_path": hermes_path,
        "toolsets": settings.HERMES_TOOLSETS,
        "grader_toolsets": settings.GRADER_TOOLSETS,
        "unattended": settings.HERMES_UNATTENDED,
        "mcp_server": "alibaba-cloud-ops-mcp-server",
        "mcp_configured": mcp_configured(),
        "mcp_servers": {
            ALIBABA_MCP_SERVER_NAME: mcp_configured(ALIBABA_MCP_SERVER_NAME),
            K3S_MCP_SERVER_NAME: mcp_configured(K3S_MCP_SERVER_NAME),
            RUM_MCP_SERVER_NAME: mcp_configured(RUM_MCP_SERVER_NAME),
            RUM2_MCP_SERVER_NAME: mcp_configured(RUM2_MCP_SERVER_NAME),
            MULTI_CLOUD_SSH_MCP_SERVER_NAME: mcp_configured(MULTI_CLOUD_SSH_MCP_SERVER_NAME),
        },
        "uvx_path": uvx_path,
    }
    if settings.HERMES_DOCKER_ENABLED and docker_path:
        try:
            completed = subprocess.run(
                [docker_path, "image", "inspect", settings.HERMES_DOCKER_IMAGE],
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
            status["docker_image_present"] = completed.returncode == 0
            if completed.returncode != 0:
                status["docker_image_error"] = (completed.stderr or completed.stdout or "").strip()[:500]
        except Exception as exc:
            status["docker_error"] = str(exc)
    elif hermes_path:
        try:
            completed = subprocess.run([hermes_path, "--version"], text=True, capture_output=True, timeout=15, check=False)
            status["version_output"] = (completed.stdout or completed.stderr or "").strip()
            status["returncode"] = completed.returncode
        except Exception as exc:
            status["error"] = str(exc)
    return status
