#!/bin/bash
# 10 - 部署 OJ 平台并绑定靶场 kubeconfig/MCP

if [[ "${OJ_ENABLED:-false}" != "true" ]]; then
  log "OJ_ENABLED=false, 跳过 OJ 部署"
  return 0 2>/dev/null || exit 0
fi

# OJ 默认部署到 SERVER1（如果未单独配置）
OJ_IP="${OJ_IP:-${SERVER1_IP:-}}"
OJ_USER="${OJ_USER:-${SERVER1_USER:-root}}"
OJ_PASS="${OJ_PASS:-${SERVER1_PASS:-}}"
OJ_KEY="${OJ_KEY:-${SERVER1_KEY:-}}"

if [[ -z "${OJ_IP}" ]]; then
  err "OJ_ENABLED=true 但 OJ_IP 和 SERVER1_IP 均未配置"
  exit 1
fi

GEN_DIR="$SCRIPT_DIR/kubeconfigs/generated"
READONLY_KUBECONFIG="$GEN_DIR/config-readonly.yaml"
INJECTOR_KUBECONFIG="$GEN_DIR/config-injector.yaml"

if [[ ! -s "$READONLY_KUBECONFIG" || ! -s "$INJECTOR_KUBECONFIG" ]]; then
  err "OJ 所需 kubeconfig 不存在，请先完成 08-generate-access"
  err "  $READONLY_KUBECONFIG"
  err "  $INJECTOR_KUBECONFIG"
  exit 1
fi

OJ_USER="${OJ_USER:-root}"
OJ_KEY="${OJ_KEY:-}"
OJ_PASS="${OJ_PASS:-}"
OJ_APP_DIR="${OJ_APP_DIR:-/opt/oj-platform}"
OJ_ENV_FILE="${OJ_ENV_FILE:-/etc/oj-platform.env}"
OJ_PORT="${OJ_PORT:-8090}"
OJ_ADMIN_USERNAME="${OJ_ADMIN_USERNAME:-admin}"
OJ_ADMIN_PASSWORD="${OJ_ADMIN_PASSWORD:-dev-admin-password}"
OJ_REGISTRATION_INVITE_CODE="${OJ_REGISTRATION_INVITE_CODE:-dev-invite-code}"
OJ_JWT_SECRET="${OJ_JWT_SECRET:-change-me-at-least-32-random-bytes-for-oj}"
OJ_GRADER_BASE_URL="${OJ_GRADER_BASE_URL:-https://api.example.com/v1}"
OJ_GRADER_MODEL="${OJ_GRADER_MODEL:-grader-model-name}"
OJ_GRADER_API_KEY="${OJ_GRADER_API_KEY:-replace-with-grader-key}"
OJ_HERMES_DOCKER_IMAGE="${OJ_HERMES_DOCKER_IMAGE:-hermes-agent:latest}"

sudo_prefix="$(remote_priv_prefix "$OJ_USER")"

systemd_env_line() {
  local key="$1"
  local value="$2"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '%s="%s"\n' "$key" "$value"
}

log "部署 OJ 平台到 ${OJ_USER}@${OJ_IP}:${OJ_APP_DIR}..."

tar_file="/tmp/oj-platform.tar.gz"
env_file="$(mktemp /tmp/oj-platform.env.XXXXXX)"
service_file="$(mktemp /tmp/oj-platform.service.XXXXXX)"

{
  systemd_env_line "OJ_ENV" "production"
  systemd_env_line "PORT" "$OJ_PORT"
  systemd_env_line "OJ_DB_FILE" "$OJ_APP_DIR/state/oj.sqlite3"
  systemd_env_line "OJ_ADMIN_USERNAME" "$OJ_ADMIN_USERNAME"
  systemd_env_line "OJ_ADMIN_PASSWORD" "$OJ_ADMIN_PASSWORD"
  systemd_env_line "OJ_REGISTRATION_INVITE_CODE" "$OJ_REGISTRATION_INVITE_CODE"
  systemd_env_line "OJ_JWT_SECRET" "$OJ_JWT_SECRET"
  systemd_env_line "OJ_GRADER_BASE_URL" "$OJ_GRADER_BASE_URL"
  systemd_env_line "OJ_GRADER_MODEL" "$OJ_GRADER_MODEL"
  systemd_env_line "OJ_GRADER_API_KEY" "$OJ_GRADER_API_KEY"
  systemd_env_line "OJ_GRADER_LABEL" "Platform grading API"
  systemd_env_line "OJ_HERMES_DOCKER" "1"
  systemd_env_line "OJ_HERMES_DOCKER_IMAGE" "$OJ_HERMES_DOCKER_IMAGE"
  systemd_env_line "OJ_HERMES_DOCKER_NETWORK" "bridge"
  systemd_env_line "OJ_HERMES_TOOLSETS" "terminal"
  systemd_env_line "OJ_K3S_READONLY_KUBECONFIG" "$OJ_APP_DIR/.kube/config-readonly.yaml"
  systemd_env_line "OJ_K3S_MCP_RUNTIME_DIR" "$OJ_APP_DIR/runtime/k3s-mcp-wrapper"
  systemd_env_line "OJ_K3S_ALLOWED_CONTEXTS" "server1,server2,server3,alicloud,tencent,aws"
  systemd_env_line "KUBECONFIG" "$OJ_APP_DIR/.kube/config-injector.yaml"
  systemd_env_line "PATH" "/root/.local/bin:/usr/local/bin:/usr/bin:/bin"
} > "$env_file"

cat > "$service_file" <<EOF
[Unit]
Description=AIOps OJ Platform
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$OJ_APP_DIR
EnvironmentFile=$OJ_ENV_FILE
Environment=PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/python3 $OJ_APP_DIR/server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

tar \
  --exclude=".git" \
  --exclude=".DS_Store" \
  --exclude="__pycache__" \
  --exclude="*/__pycache__" \
  --exclude="state" \
  --exclude="images" \
  --exclude="rendered" \
  --exclude="kubeconfigs/generated" \
  --exclude="*.tar" \
  --exclude="*.tar.gz" \
  -czf "$tar_file" \
  -C "$SCRIPT_DIR" .

scp_upload "$tar_file" "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "/tmp/oj-platform.tar.gz"
rm -f "$tar_file"

# 预构建 Hermes 镜像（如果存在则上传，部署时 docker load）
hermes_image_tar="$SCRIPT_DIR/docker/hermes-agent-image.tar.gz"
if [[ -f "$hermes_image_tar" ]]; then
  log "上传预构建 Hermes 镜像 ($(du -h "$hermes_image_tar" | cut -f1))..."
  scp_upload "$hermes_image_tar" "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "/tmp/hermes-agent-image.tar.gz"
fi

scp_upload "$READONLY_KUBECONFIG" "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "/tmp/config-readonly.yaml"
scp_upload "$INJECTOR_KUBECONFIG" "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "/tmp/config-injector.yaml"
scp_upload "$env_file" "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "/tmp/oj-platform.env"
scp_upload "$service_file" "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "/tmp/oj-platform.service"
rm -f "$env_file" "$service_file"

ssh_exec "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "
  set -e
  ${sudo_prefix}mkdir -p '$OJ_APP_DIR' '$OJ_APP_DIR/.kube' '$OJ_APP_DIR/state'
  ${sudo_prefix}tar -xzf /tmp/oj-platform.tar.gz -C '$OJ_APP_DIR'
  ${sudo_prefix}mkdir -p '$OJ_APP_DIR/docker'
  if [ -f /tmp/hermes-agent-image.tar.gz ]; then
    ${sudo_prefix}mv /tmp/hermes-agent-image.tar.gz '$OJ_APP_DIR/docker/hermes-agent-image.tar.gz'
  fi
  ${sudo_prefix}mv /tmp/config-readonly.yaml '$OJ_APP_DIR/.kube/config-readonly.yaml'
  ${sudo_prefix}mv /tmp/config-injector.yaml '$OJ_APP_DIR/.kube/config-injector.yaml'
  ${sudo_prefix}chmod 600 '$OJ_APP_DIR/.kube/config-readonly.yaml' '$OJ_APP_DIR/.kube/config-injector.yaml'
  ${sudo_prefix}mkdir -p /root/.kube
  ${sudo_prefix}cp '$OJ_APP_DIR/.kube/config-readonly.yaml' /root/.kube/config-readonly.yaml
  ${sudo_prefix}cp '$OJ_APP_DIR/.kube/config-injector.yaml' /root/.kube/config-injector.yaml
  ${sudo_prefix}chmod 600 /root/.kube/config-readonly.yaml /root/.kube/config-injector.yaml

  # --- Python 基础依赖 + sqlite3 ---
  if command -v apt-get >/dev/null 2>&1; then
    ${sudo_prefix}apt-get update
    ${sudo_prefix}apt-get install -y python3 python3-venv python3-pip curl ca-certificates sqlite3 2>/dev/null || \
    ${sudo_prefix}apt-get install -y python3 python3-venv python3-pip curl ca-certificates
  fi

  # --- Docker CE 安装（国内可用 + 完整性校验）---
  # 检查 dockerd 二进制是否存在（有些情况包装好了但二进制缺失）
  docker_ok=false
  if command -v docker >/dev/null 2>&1 && command -v dockerd >/dev/null 2>&1; then
    docker_ok=true
  fi
  if [ \"\$docker_ok\" = \"false\" ]; then
    echo \"[deploy] Installing Docker CE...\"
    # 优先用官方脚本 + 阿里云镜像
    curl --http1.1 -fsSL https://get.docker.com -o /tmp/get-docker.sh 2>/dev/null || true
    if [ -s /tmp/get-docker.sh ]; then
      ${sudo_prefix}sh /tmp/get-docker.sh --mirror Aliyun 2>&1 || true
      rm -f /tmp/get-docker.sh
    fi
    # 如果仍缺 dockerd，尝试直接装包（适用于已添加过 Docker repo 的机器）
    if ! command -v dockerd >/dev/null 2>&1; then
      ${sudo_prefix}apt-get install -y --reinstall docker-ce docker-ce-cli containerd.io 2>/dev/null || true
    fi
    # 最后兜底：docker.io（Ubuntu 官方源）
    if ! command -v dockerd >/dev/null 2>&1; then
      ${sudo_prefix}apt-get install -y docker.io 2>/dev/null || true
    fi
    ${sudo_prefix}systemctl enable --now docker 2>/dev/null || true
    # 确保客户端也在
    if ! command -v docker >/dev/null 2>&1; then
      ${sudo_prefix}apt-get install -y --reinstall docker-ce-cli 2>/dev/null || true
    fi
  fi

  # --- Docker daemon 就绪检查 ---
  if command -v docker >/dev/null 2>&1 && command -v dockerd >/dev/null 2>&1; then
    echo \"[deploy] Waiting for Docker daemon...\"
    for i in 1 2 3 4 5 6 7 8 9 10; do
      if docker info >/dev/null 2>&1; then
        echo \"[deploy] Docker daemon is ready\"
        break
      fi
      if [ \"\$i\" -eq 10 ]; then
        echo \"[deploy] ERROR: Docker daemon failed to start after 10 retries\" >&2
        ${sudo_prefix}systemctl status docker --no-pager 2>/dev/null || true
      fi
      sleep 2
    done
  else
    echo \"[deploy] ERROR: Docker CE installation failed - dockerd binary not found\" >&2
    echo \"[deploy] Hermes agent will NOT be available. Please install Docker manually.\" >&2
  fi

  # --- Docker Hub 国内镜像加速 ---
  if command -v docker >/dev/null 2>&1; then
    if ! ${sudo_prefix}test -f /etc/docker/daemon.json || ! ${sudo_prefix}grep -q registry-mirrors /etc/docker/daemon.json 2>/dev/null; then
      echo '[deploy] Configuring Docker Hub mirrors for China...'
      echo '{\"registry-mirrors\":[\"https://registry.cn-guangzhou.aliyuncs.com\",\"https://docker.1ms.run\",\"https://docker.xuanyuan.me\"]}' | ${sudo_prefix}tee /etc/docker/daemon.json >/dev/null
      ${sudo_prefix}systemctl daemon-reload 2>/dev/null || true
      ${sudo_prefix}systemctl restart docker 2>/dev/null || true
      sleep 3
    fi
  fi

  if ! command -v kubectl >/dev/null 2>&1; then
    tmp_kubectl=/tmp/kubectl
    curl --http1.1 -fsSL -o \"\$tmp_kubectl\" 'https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl'
    ${sudo_prefix}install -m 0755 \"\$tmp_kubectl\" /usr/local/bin/kubectl
    rm -f \"\$tmp_kubectl\"
  fi

  # 自动检测 kubectl 实际路径并写入 env（k3s 安装的 kubectl 可能在 /usr/bin）
  kubectl_real_path=\$(command -v kubectl 2>/dev/null || echo \"/usr/local/bin/kubectl\")
  echo \"OJ_K3S_KUBECTL_PATH=\"${kubectl_real_path}\"\" | ${sudo_prefix}tee -a /tmp/oj-platform.env >/dev/null

  # --- Hermes Agent 镜像（优先加载预构建 tar，否则在线 build）---
  target_image='$OJ_HERMES_DOCKER_IMAGE'
  hermes_image_tar='$OJ_APP_DIR/docker/hermes-agent-image.tar.gz'
  hermes_ready=false
  if ${sudo_prefix}test -f \"\$hermes_image_tar\"; then
    echo \"[deploy] Loading pre-built Hermes image from tar...\"
    loaded=\$(${sudo_prefix}docker load -i \"\$hermes_image_tar\" 2>&1) || true
    if echo \"\$loaded\" | grep -q \"Loaded image\"; then
      # docker load 可能加载为不同 tag，统一 re-tag 为目标名
      loaded_tag=\$(echo \"\$loaded\" | grep \"Loaded image\" | sed 's/Loaded image: //')
      if [ \"\$loaded_tag\" != \"\$target_image\" ]; then
        echo \"[deploy] Re-tagging \$loaded_tag -> \$target_image\"
        ${sudo_prefix}docker tag \"\$loaded_tag\" \"\$target_image\"
      fi
      hermes_ready=true
    else
      echo \"[deploy] WARNING: docker load failed: \$loaded\" >&2
    fi
  fi
  if [ \"\$hermes_ready\" = \"false\" ] && command -v docker >/dev/null 2>&1 && ${sudo_prefix}test -f '$OJ_APP_DIR/docker/hermes-runtime.Dockerfile'; then
    echo \"[deploy] Building Hermes runtime image (includes hermes-agent from GitHub)...\"
    if ${sudo_prefix}docker build \
      --build-arg APT_MIRROR=http://mirrors.aliyun.com \
      --build-arg PIP_INDEX_URL=http://mirrors.aliyun.com/pypi/simple/ \
      --build-arg PIP_TRUSTED_HOST=mirrors.aliyun.com \
      -t \"\$target_image\" \
      -f '$OJ_APP_DIR/docker/hermes-runtime.Dockerfile' \
      '$OJ_APP_DIR'; then
      hermes_ready=true
    else
      echo \"[deploy] ERROR: Hermes image build failed\" >&2
    fi
  fi
  if [ \"\$hermes_ready\" = \"false\" ]; then
    echo \"[deploy] WARNING: Hermes Docker image not available - agent submissions will fail\" >&2
  else
    echo \"[deploy] Hermes image ready: \$target_image\"
    # 验证镜像可用
    ${sudo_prefix}docker run --rm \"\$target_image\" /opt/hermes-agent/venv/bin/python --version 2>/dev/null || \
      echo \"[deploy] WARNING: Hermes image python check failed\"
  fi

  ${sudo_prefix}mv /tmp/oj-platform.env '$OJ_ENV_FILE'
  ${sudo_prefix}chmod 600 '$OJ_ENV_FILE'

  ${sudo_prefix}mv /tmp/oj-platform.service /etc/systemd/system/oj-platform.service
  ${sudo_prefix}systemctl daemon-reload
  ${sudo_prefix}systemctl enable --now oj-platform
  sleep 3
  ${sudo_prefix}systemctl --no-pager --full status oj-platform || true
  rm -f /tmp/oj-platform.tar.gz
"

log "OJ 平台部署完成: http://${OJ_IP}:${OJ_PORT}"
log "OJ 已绑定:"
log "  readonly kubeconfig: ${OJ_APP_DIR}/.kube/config-readonly.yaml"
log "  injector kubeconfig: ${OJ_APP_DIR}/.kube/config-injector.yaml"
