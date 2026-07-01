#!/bin/bash
# ============================================================
# 公共函数库 — 被所有子脚本 source
# ============================================================

# SSH 执行封装（自动选择密码/密钥）
ssh_exec() {
  local host="$1"; shift
  local user="$1"; shift
  local pass_var="$1"; shift
  local key_var="$1"; shift

  local key="${!key_var:-}"
  local pass="${!pass_var:-}"

  if [[ -n "$key" && -f "$key" ]]; then
    ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i "$key" "${user}@${host}" "$@"
  elif [[ -n "$pass" ]]; then
    sshpass -p "$pass" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "${user}@${host}" "$@"
  else
    err "无可用凭据连接 ${user}@${host}"
    return 1
  fi
}

# 三台服务器并发 SSH 执行
ssh_all_parallel() {
  local cmd="$@"
  ssh_exec "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" "$cmd" &
  local pid1=$!
  ssh_exec "$TENCENT_IP" "$TENCENT_USER" "TENCENT_PASS" "TENCENT_KEY" "$cmd" &
  local pid2=$!
  ssh_exec "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" "$cmd" &
  local pid3=$!

  local fail=0
  wait $pid1 || { err "阿里云执行失败"; fail=1; }
  wait $pid2 || { err "腾讯云执行失败"; fail=1; }
  wait $pid3 || { err "AWS 执行失败"; fail=1; }
  return $fail
}

# SCP 上传封装
scp_upload() {
  local local_path="$1"
  local host="$2"
  local user="$3"
  local pass_var="$4"
  local key_var="$5"
  local remote_path="$6"

  local key="${!key_var:-}"
  local pass="${!pass_var:-}"

  if [[ -n "$key" && -f "$key" ]]; then
    scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 -i "$key" "$local_path" "${user}@${host}:${remote_path}"
  elif [[ -n "$pass" ]]; then
    sshpass -p "$pass" scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 "$local_path" "${user}@${host}:${remote_path}"
  else
    err "无可用凭据上传 ${local_path} 到 ${user}@${host}:${remote_path}"
    return 1
  fi
}

scp_download() {
  local host="$1"
  local user="$2"
  local pass_var="$3"
  local key_var="$4"
  local remote_path="$5"
  local local_path="$6"

  local key="${!key_var:-}"
  local pass="${!pass_var:-}"

  if [[ -n "$key" && -f "$key" ]]; then
    scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 -i "$key" "${user}@${host}:${remote_path}" "$local_path"
  elif [[ -n "$pass" ]]; then
    sshpass -p "$pass" scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 "${user}@${host}:${remote_path}" "$local_path"
  else
    err "无可用凭据下载 ${user}@${host}:${remote_path}"
    return 1
  fi
}

remote_priv_prefix() {
  local user="$1"
  [[ "$user" == "root" ]] && echo "" || echo "sudo -n "
}

# kubectl 封装（根据云选择连接信息和 sudo）
kubectl_for() {
  local cloud="$1"; shift
  local ip user pass_var key_var

  case "$cloud" in
    aliyun)  ip="$ALIYUN_IP";  user="$ALIYUN_USER";  pass_var="ALIYUN_PASS";  key_var="ALIYUN_KEY" ;;
    tencent) ip="$TENCENT_IP"; user="$TENCENT_USER"; pass_var="TENCENT_PASS"; key_var="TENCENT_KEY" ;;
    aws)     ip="$AWS_IP";     user="$AWS_USER";     pass_var="AWS_PASS";     key_var="AWS_KEY" ;;
    *) err "未知云: $cloud"; return 1 ;;
  esac

  local sudo_prefix
  sudo_prefix="$(remote_priv_prefix "$user")"
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "${sudo_prefix}k3s kubectl $*"
}

# 等待 Pod Ready
wait_for_pods() {
  local cloud="$1"
  local ns="${2:-seat-1}"
  local timeout="${3:-300}"

  log "等待 ${cloud} ${ns} 所有 Pod Ready (超时 ${timeout}s)..."
  local elapsed=0
  while [[ $elapsed -lt $timeout ]]; do
    local not_ready
    not_ready=$(kubectl_for "$cloud" "get pods -n $ns --no-headers 2>/dev/null | grep -v Running | grep -v Completed | wc -l" || echo "99")
    if [[ "$not_ready" -eq 0 ]]; then
      log "${cloud} ${ns} 所有 Pod 已 Ready"
      return 0
    fi
    sleep 10
    elapsed=$((elapsed + 10))
  done
  warn "${cloud} ${ns} 超时，仍有 Pod 未 Ready"
  kubectl_for "$cloud" "get pods -n $ns"
  return 1
}
