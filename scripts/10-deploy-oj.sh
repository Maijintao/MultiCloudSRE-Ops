#!/bin/bash
# 10 - 部署 OJ 平台并绑定靶场 kubeconfig/MCP

if [[ "${OJ_ENABLED:-false}" != "true" ]]; then
  log "OJ_ENABLED=false, 跳过 OJ 部署"
  return 0 2>/dev/null || exit 0
fi

if [[ -z "${OJ_IP:-}" ]]; then
  err "OJ_ENABLED=true 但 OJ_IP 未配置"
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
  systemd_env_line "MC_ALIYUN_HOST" "$SERVER1_IP"
  systemd_env_line "MC_ALIYUN_USER" "$SERVER1_USER"
  systemd_env_line "MC_TENCENT_HOST" "$SERVER2_IP"
  systemd_env_line "MC_TENCENT_USER" "$SERVER2_USER"
  systemd_env_line "OJ_MULTI_CLOUD_MCP_RUNTIME_DIR" "$OJ_APP_DIR/runtime/multi-cloud-ssh-mcp"
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

scp_upload "$READONLY_KUBECONFIG" "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "/tmp/config-readonly.yaml"
scp_upload "$INJECTOR_KUBECONFIG" "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "/tmp/config-injector.yaml"
scp_upload "$env_file" "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "/tmp/oj-platform.env"
scp_upload "$service_file" "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "/tmp/oj-platform.service"
rm -f "$env_file" "$service_file"

ssh_exec "$OJ_IP" "$OJ_USER" "OJ_PASS" "OJ_KEY" "
  set -e
  ${sudo_prefix}mkdir -p '$OJ_APP_DIR' '$OJ_APP_DIR/.kube' '$OJ_APP_DIR/state'
  ${sudo_prefix}tar -xzf /tmp/oj-platform.tar.gz -C '$OJ_APP_DIR'
  ${sudo_prefix}mv /tmp/config-readonly.yaml '$OJ_APP_DIR/.kube/config-readonly.yaml'
  ${sudo_prefix}mv /tmp/config-injector.yaml '$OJ_APP_DIR/.kube/config-injector.yaml'
  ${sudo_prefix}chmod 600 '$OJ_APP_DIR/.kube/config-readonly.yaml' '$OJ_APP_DIR/.kube/config-injector.yaml'
  ${sudo_prefix}mkdir -p /root/.kube
  ${sudo_prefix}cp '$OJ_APP_DIR/.kube/config-readonly.yaml' /root/.kube/config-readonly.yaml
  ${sudo_prefix}cp '$OJ_APP_DIR/.kube/config-injector.yaml' /root/.kube/config-injector.yaml
  ${sudo_prefix}chmod 600 /root/.kube/config-readonly.yaml /root/.kube/config-injector.yaml

  if command -v apt-get >/dev/null 2>&1; then
    ${sudo_prefix}apt-get update
    ${sudo_prefix}apt-get install -y python3 python3-venv python3-pip curl ca-certificates
    if ! command -v docker >/dev/null 2>&1; then
      ${sudo_prefix}apt-get install -y docker.io
      ${sudo_prefix}systemctl enable --now docker || true
    fi
  fi

  if ! command -v kubectl >/dev/null 2>&1; then
    tmp_kubectl=/tmp/kubectl
    curl -fsSL -o \"\$tmp_kubectl\" 'https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl'
    ${sudo_prefix}install -m 0755 \"\$tmp_kubectl\" /usr/local/bin/kubectl
    rm -f \"\$tmp_kubectl\"
  fi

  if command -v docker >/dev/null 2>&1 && [[ -f '$OJ_APP_DIR/docker/hermes-runtime.Dockerfile' ]]; then
    ${sudo_prefix}docker build -t '$OJ_HERMES_DOCKER_IMAGE' -f '$OJ_APP_DIR/docker/hermes-runtime.Dockerfile' '$OJ_APP_DIR' || true
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
