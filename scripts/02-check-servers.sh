#!/bin/bash
# 02 - 检查三台服务器 SSH 连通性 + 跨云端口连通

log "检查三台服务器 SSH 连通性..."

check_ssh() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"
  if ssh_exec "$ip" "$user" "$pass_var" "$key_var" "echo ok" &>/dev/null; then
    log "  $label ($ip): SSH 连接成功"
  else
    err "  $label ($ip): SSH 连接失败"
    return 1
  fi
}

check_ssh "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" "阿里云" || exit 1
check_ssh "$TENCENT_IP" "$TENCENT_USER" "TENCENT_PASS" "TENCENT_KEY" "腾讯云" || exit 1
check_ssh "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" "AWS" || exit 1

log "检查服务器基础环境..."

check_env() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    echo '=== OS ===' && cat /etc/os-release | grep PRETTY_NAME
    echo '=== Arch ===' && uname -m
    echo '=== Memory ===' && free -h | head -2
    echo '=== Disk ===' && df -h / | tail -1
    echo '=== Sudo ===' && sudo -n echo ok 2>/dev/null || echo 'needs password'
  "
}

log "阿里云环境:"
check_env "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" "阿里云"

log "腾讯云环境:"
check_env "$TENCENT_IP" "$TENCENT_USER" "TENCENT_PASS" "TENCENT_KEY" "腾讯云"

log "AWS 环境:"
check_env "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" "AWS"

log "服务器检查通过"
