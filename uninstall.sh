#!/bin/bash
set -euo pipefail

# ============================================================
# SRE-OJ 多云靶场 — 交互式卸载
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# 加载 lib.sh
source "$SCRIPTS_DIR/lib.sh"

# bash 3.2 兼容：替代 $(role_upper "$role")
role_upper() {
  case "$1" in
    server1) echo "SERVER1" ;;
    server2) echo "SERVER2" ;;
    server3) echo "SERVER3" ;;
  esac
}

# 加载 config.env
if [[ -f "$SCRIPT_DIR/config.env" ]]; then
  source "$SCRIPT_DIR/config.env"
else
  err "config.env 不存在，请先运行 ./deploy.sh 或手动创建"
  exit 1
fi

banner() {
  echo -e "${BLUE}"
  echo "  ╔══════════════════════════════════════════╗"
  echo "  ║     SRE-OJ 多云靶场 交互式卸载           ║"
  echo "  ╚══════════════════════════════════════════╝"
  echo -e "${NC}"
}

confirm() {
  local prompt="$1"
  local reply
  read -r -p "$prompt [y/N]: " reply
  [[ "$reply" =~ ^[Yy] ]]
}

# ============================================================
# 卸载函数
# ============================================================

uninstall_oj() {
  local oj_ip="${OJ_IP:-${SERVER1_IP}}"
  local oj_user="${OJ_USER:-${SERVER1_USER}}"
  local oj_pass_var="OJ_PASS"
  local oj_key_var="OJ_KEY"
  # 如果 OJ 配置为空，回退到 server1
  [[ -z "${!oj_pass_var:-}" ]] && oj_pass_var="SERVER1_PASS"
  [[ -z "${!oj_key_var:-}" ]] && oj_key_var="SERVER1_KEY"

  local oj_app_dir="${OJ_APP_DIR:-/opt/oj-platform}"
  local oj_env_file="${OJ_ENV_FILE:-/etc/oj-platform.env}"
  local sudo_prefix
  sudo_prefix="$(remote_priv_prefix "$oj_user")"

  log "卸载 OJ 平台 (${oj_user}@${oj_ip})..."

  ssh_exec "$oj_ip" "$oj_user" "$oj_pass_var" "$oj_key_var" "
    ${sudo_prefix}systemctl stop oj-platform 2>/dev/null || true
    ${sudo_prefix}systemctl disable oj-platform 2>/dev/null || true
    ${sudo_prefix}rm -f /etc/systemd/system/oj-platform.service
    ${sudo_prefix}systemctl daemon-reload
    ${sudo_prefix}rm -f '$oj_env_file'
    # 清理 Docker 镜像
    ${sudo_prefix}docker rmi '${OJ_HERMES_DOCKER_IMAGE:-hermes-agent:latest}' 2>/dev/null || true
    echo 'OJ 平台已卸载'
  " || { err "OJ 卸载失败"; return 1; }

  log "OJ 平台卸载完成"
}

uninstall_targets() {
  log "删除靶场服务（namespace: seat-1）..."

  local unique_hosts=()
  local host_users=()
  local host_pass_vars=()
  local host_key_vars=()

  # 收集唯一的主机
  for role in server1 server2 server3; do
    local ip_var="$(role_upper "$role")_IP"
    local user_var="$(role_upper "$role")_USER"
    local pass_var="$(role_upper "$role")_PASS"
    local key_var="$(role_upper "$role")_KEY"
    local ip="${!ip_var}" user="${!user_var}"

    local already_added=false
    if [[ ${#unique_hosts[@]} -gt 0 ]]; then
      for h in "${unique_hosts[@]}"; do
        [[ "$h" == "$ip" ]] && already_added=true && break
      done
    fi

    if [[ "$already_added" == "false" ]]; then
      unique_hosts+=("$ip")
      host_users+=("$user")
      host_pass_vars+=("$(role_upper "$role")_PASS")
      host_key_vars+=("$(role_upper "$role")_KEY")
    fi
  done

  for i in "${!unique_hosts[@]}"; do
    local ip="${unique_hosts[$i]}"
    local user="${host_users[$i]}"
    local pass_var="${host_pass_vars[$i]}"
    local key_var="${host_key_vars[$i]}"
    local sudo_prefix
    sudo_prefix="$(remote_priv_prefix "$user")"

    log "  清理 ${user}@${ip} 上的 seat-1 namespace..."
    ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
      if command -v kubectl >/dev/null 2>&1; then
        ${sudo_prefix}kubectl delete namespace seat-1 --timeout=120s 2>/dev/null || true
      else
        ${sudo_prefix}k3s kubectl delete namespace seat-1 --timeout=120s 2>/dev/null || true
      fi
      echo '  ${ip}: seat-1 namespace 已删除'
    " || warn "  ${ip}: 清理失败（可能 k3s 已不存在）"
  done

  log "靶场服务卸载完成"
}

uninstall_chaos_mesh() {
  log "卸载 Chaos Mesh..."

  local unique_hosts=()
  local host_users=()
  local host_pass_vars=()
  local host_key_vars=()

  for role in server1 server2 server3; do
    local ip_var="$(role_upper "$role")_IP"
    local user_var="$(role_upper "$role")_USER"
    local ip="${!ip_var}" user="${!user_var}"

    local already_added=false
    if [[ ${#unique_hosts[@]} -gt 0 ]]; then
      for h in "${unique_hosts[@]}"; do
        [[ "$h" == "$ip" ]] && already_added=true && break
      done
    fi

    if [[ "$already_added" == "false" ]]; then
      unique_hosts+=("$ip")
      host_users+=("$user")
      host_pass_vars+=("$(role_upper "$role")_PASS")
      host_key_vars+=("$(role_upper "$role")_KEY")
    fi
  done

  for i in "${!unique_hosts[@]}"; do
    local ip="${unique_hosts[$i]}"
    local user="${host_users[$i]}"
    local pass_var="${host_pass_vars[$i]}"
    local key_var="${host_key_vars[$i]}"
    local sudo_prefix
    sudo_prefix="$(remote_priv_prefix "$user")"

    log "  清理 ${user}@${ip} 上的 Chaos Mesh..."
    ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
      if command -v helm >/dev/null 2>&1; then
        helm uninstall chaos-mesh -n chaos-mesh 2>/dev/null || true
      fi
      if command -v kubectl >/dev/null 2>&1; then
        ${sudo_prefix}kubectl delete namespace chaos-mesh --timeout=120s 2>/dev/null || true
      else
        ${sudo_prefix}k3s kubectl delete namespace chaos-mesh --timeout=120s 2>/dev/null || true
      fi
      echo '  ${ip}: Chaos Mesh 已卸载'
    " || warn "  ${ip}: Chaos Mesh 卸载失败"
  done

  log "Chaos Mesh 卸载完成"
}

uninstall_k3s() {
  log "卸载 k3s..."

  for role in server1 server2 server3; do
    local ip_var="$(role_upper "$role")_IP"
    local user_var="$(role_upper "$role")_USER"
    local pass_var="$(role_upper "$role")_PASS"
    local key_var="$(role_upper "$role")_KEY"
    local ip="${!ip_var}" user="${!user_var}"
    local sudo_prefix
    sudo_prefix="$(remote_priv_prefix "$user")"

    log "  卸载 ${role} (${user}@${ip}) 上的 k3s..."
    ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
      # k3s 官方卸载脚本
      if [ -f /usr/local/bin/k3s-uninstall.sh ]; then
        ${sudo_prefix}/usr/local/bin/k3s-uninstall.sh
      fi
      if [ -f /usr/local/bin/k3s-agent-uninstall.sh ]; then
        ${sudo_prefix}/usr/local/bin/k3s-agent-uninstall.sh
      fi
      # 清理残留
      ${sudo_prefix}rm -rf /etc/rancher /var/lib/rancher /var/lib/kubelet
      ${sudo_prefix}rm -f /usr/local/bin/k3s /usr/bin/kubectl
      ${sudo_prefix}rm -f /etc/systemd/system/k3s.service /etc/systemd/system/k3s-agent.service
      ${sudo_prefix}systemctl daemon-reload 2>/dev/null || true
      echo '  ${ip}: k3s 已卸载'
    " || warn "  ${ip}: k3s 卸载失败"
  done

  # 清理本地 kubeconfig
  local gen_dir="$SCRIPT_DIR/kubeconfigs/generated"
  if [[ -d "$gen_dir" ]]; then
    rm -rf "$gen_dir"
    log "  已清理本地 kubeconfig: $gen_dir"
  fi

  log "k3s 卸载完成"
}

# ============================================================
# 主流程
# ============================================================

banner

echo "即将卸载以下组件（输入 y 确认，直接回车跳过）："
echo ""

do_oj=false
do_targets=false
do_chaos=false
do_k3s=false

if confirm "  [1/4] 删除 OJ 平台（评测服务 + Hermes 镜像）?"; then
  do_oj=true
fi
if confirm "  [2/4] 删除靶场服务（seat-1 namespace 中的所有工作负载）?"; then
  do_targets=true
fi
if confirm "  [3/4] 删除 Chaos Mesh（故障注入框架）?"; then
  do_chaos=true
fi
if confirm "  [4/4] 删除 k3s（Kubernetes 集群，会清除所有容器数据）?"; then
  do_k3s=true
fi

echo ""

if [[ "$do_oj" == "false" && "$do_targets" == "false" && "$do_chaos" == "false" && "$do_k3s" == "false" ]]; then
  log "未选择任何组件，退出。"
  exit 0
fi

if confirm "确认执行以上卸载操作? (此操作不可逆)"; then
  :
else
  log "已取消。"
  exit 0
fi

echo ""

# 按依赖顺序卸载：OJ → 靶场 → Chaos Mesh → k3s
[[ "$do_oj" == "true" ]]      && uninstall_oj
[[ "$do_targets" == "true" ]] && uninstall_targets
[[ "$do_chaos" == "true" ]]   && uninstall_chaos_mesh
[[ "$do_k3s" == "true" ]]     && uninstall_k3s

echo ""
log "卸载完成！"
