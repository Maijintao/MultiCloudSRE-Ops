#!/bin/bash
# ============================================================
# 公共函数库 — 被所有子脚本 source
# ============================================================

_ssh_opts="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o PreferredAuthentications=password,keyboard-interactive -o PubkeyAuthentication=no"

ssh_exec() {
  local host="$1"; shift
  local user="$1"; shift
  local pass_var="$1"; shift
  local key_var="$1"; shift

  local key="${!key_var:-}"
  local pass="${!pass_var:-}"
  local attempt rc

  if [[ -n "$key" && -f "$key" ]]; then
    ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i "$key" "${user}@${host}" "$@"
  elif [[ -n "$pass" ]]; then
    for attempt in 1 2 3; do
      sshpass -p "$pass" ssh $_ssh_opts "${user}@${host}" "$@"
      rc=$?
      [[ $rc -eq 0 ]] && return 0
      [[ $attempt -lt 3 ]] && sleep 2
    done
    return $rc
  else
    err "无可用凭据连接 ${user}@${host}"
    return 1
  fi
}

role_upper() {
  case "$1" in
    server1) echo "SERVER1" ;;
    server2) echo "SERVER2" ;;
    server3) echo "SERVER3" ;;
  esac
}

# 三台服务器并发 SSH 执行（自动去重同 IP）
ssh_all_parallel() {
  local cmd="$@"
  local seen_ips=""
  local pids=()

  for role in server1 server2 server3; do
    local ip_var="$(role_upper "$role")_IP"
    local user_var="$(role_upper "$role")_USER"
    local pass_var="$(role_upper "$role")_PASS"
    local key_var="$(role_upper "$role")_KEY"
    local ip="${!ip_var}"

    # IP dedup
    local already=0
    for seen in $seen_ips; do
      [[ "$seen" == "$ip" ]] && already=1 && break
    done
    [[ $already -eq 1 ]] && continue
    seen_ips="$seen_ips $ip"

    ssh_exec "$ip" "${!user_var}" "$pass_var" "$key_var" "$cmd" &
    pids+=($!)
  done

  local fail=0
  for pid in "${pids[@]}"; do
    wait $pid || fail=1
  done
  return $fail
}

scp_upload() {
  local local_path="$1"
  local host="$2"
  local user="$3"
  local pass_var="$4"
  local key_var="$5"
  local remote_path="$6"

  local key="${!key_var:-}"
  local pass="${!pass_var:-}"
  local attempt rc

  if [[ -n "$key" && -f "$key" ]]; then
    scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 -i "$key" "$local_path" "${user}@${host}:${remote_path}"
  elif [[ -n "$pass" ]]; then
    for attempt in 1 2 3; do
      sshpass -p "$pass" scp $_ssh_opts -o ServerAliveInterval=5 -o ServerAliveCountMax=2 "$local_path" "${user}@${host}:${remote_path}"
      rc=$?
      [[ $rc -eq 0 ]] && return 0
      [[ $attempt -lt 3 ]] && sleep 2
    done
    err "scp_upload 失败 (重试 3 次): $(basename "$local_path") -> ${user}@${host}"
    return $rc
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
  local attempt rc

  if [[ -n "$key" && -f "$key" ]]; then
    scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 -i "$key" "${user}@${host}:${remote_path}" "$local_path"
  elif [[ -n "$pass" ]]; then
    for attempt in 1 2 3; do
      sshpass -p "$pass" scp $_ssh_opts -o ServerAliveInterval=5 -o ServerAliveCountMax=2 "${user}@${host}:${remote_path}" "$local_path"
      rc=$?
      [[ $rc -eq 0 ]] && return 0
      [[ $attempt -lt 3 ]] && sleep 2
    done
    err "scp_download 失败 (重试 3 次): ${user}@${host}:${remote_path}"
    return $rc
  else
    err "无可用凭据下载 ${user}@${host}:${remote_path}"
    return 1
  fi
}

remote_priv_prefix() {
  local user="$1"
  [[ "$user" == "root" ]] && echo "" || echo "sudo -n "
}

role_key() {
  case "$1" in
    server1|aliyun)  echo "server1" ;;
    server2|tencent) echo "server2" ;;
    server3|aws)     echo "server3" ;;
    *) err "未知服务器角色: $1"; return 1 ;;
  esac
}

role_label() {
  case "$(role_key "$1")" in
    server1) echo "服务器1" ;;
    server2) echo "服务器2" ;;
    server3) echo "服务器3" ;;
  esac
}

role_cloud_dir() {
  case "$(role_key "$1")" in
    server1) echo "aliyun" ;;
    server2) echo "tencent" ;;
    server3) echo "aws" ;;
  esac
}

role_ip() {
  case "$(role_key "$1")" in
    server1) echo "$SERVER1_IP" ;;
    server2) echo "$SERVER2_IP" ;;
    server3) echo "$SERVER3_IP" ;;
  esac
}

role_user() {
  case "$(role_key "$1")" in
    server1) echo "$SERVER1_USER" ;;
    server2) echo "$SERVER2_USER" ;;
    server3) echo "$SERVER3_USER" ;;
  esac
}

role_pass_var() {
  case "$(role_key "$1")" in
    server1) echo "SERVER1_PASS" ;;
    server2) echo "SERVER2_PASS" ;;
    server3) echo "SERVER3_PASS" ;;
  esac
}

role_key_var() {
  case "$(role_key "$1")" in
    server1) echo "SERVER1_KEY" ;;
    server2) echo "SERVER2_KEY" ;;
    server3) echo "SERVER3_KEY" ;;
  esac
}

host_roles_for_ip() {
  local target_ip="$1"
  local role
  for role in server1 server2 server3; do
    if [[ "$(role_ip "$role")" == "$target_ip" ]]; then
      printf "%s " "$role"
    fi
  done
  return 0
}

unique_role_hosts() {
  local seen_ips="
"
  local role ip
  for role in server1 server2 server3; do
    ip="$(role_ip "$role")"
    [[ -n "$ip" ]] || continue
    case "$seen_ips" in
      *"
$ip
"*) ;;
      *)
        seen_ips="${seen_ips}${ip}
"
        echo "$role"
        ;;
    esac
  done
}

# kubectl 封装（根据服务器角色选择连接信息和 sudo）
kubectl_for() {
  local role="$1"; shift
  local ip user pass_var key_var

  role="$(role_key "$role")"
  ip="$(role_ip "$role")"
  user="$(role_user "$role")"
  pass_var="$(role_pass_var "$role")"
  key_var="$(role_key_var "$role")"

  local sudo_prefix
  sudo_prefix="$(remote_priv_prefix "$user")"
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "${sudo_prefix}k3s kubectl $*"
}

# 等待 Pod Ready
wait_for_pods() {
  local role="$1"
  local ns="${2:-seat-1}"
  local timeout="${3:-300}"

  log "等待 ${role} ${ns} 所有 Pod Ready (超时 ${timeout}s)..."
  if kubectl_for "$role" "wait --for=condition=Ready pods --all -n $ns --timeout=${timeout}s"; then
    log "${role} ${ns} 所有 Pod 已 Ready"
    return 0
  fi

  warn "${role} ${ns} 超时，仍有 Pod 未 Ready"
  kubectl_for "$role" "get pods -n $ns"
  return 1
}
