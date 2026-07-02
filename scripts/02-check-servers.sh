#!/bin/bash
# 02 - 检查服务器 SSH 连通性和基础环境

log "检查服务器 SSH 连通性..."

check_ssh() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"
  if ssh_exec "$ip" "$user" "$pass_var" "$key_var" "echo ok" &>/dev/null; then
    log "  $label ($ip): SSH 连接成功"
  else
    err "  $label ($ip): SSH 连接失败"
    return 1
  fi
}

check_env() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"
  local sudo_check="echo root"
  if [[ "$user" != "root" ]]; then
    sudo_check="sudo -n true && echo sudo-ok || echo sudo-missing"
  fi

  log "$label 环境:"
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    echo '=== Roles ===' && echo '$(host_roles_for_ip "$ip")'
    echo '=== OS ===' && cat /etc/os-release | grep PRETTY_NAME
    echo '=== Arch ===' && uname -m
    echo '=== Memory ===' && free -h | head -2
    echo '=== Disk ===' && df -h / | tail -1
    echo '=== Privilege ===' && $sudo_check
  "
}

check_arch() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"
  local arch

  arch="$(ssh_exec "$ip" "$user" "$pass_var" "$key_var" "uname -m" 2>/dev/null | tr -d '\r' | tail -n 1)"
  case "$arch" in
    x86_64|amd64)
      return 0
      ;;
    *)
      err "$label 架构是 $arch，但当前离线镜像按 amd64/x86_64 准备。"
      err "请使用 x86_64/amd64 Ubuntu 服务器，否则 Pod 可能 Image/exec 格式不兼容。"
      return 1
      ;;
  esac
}

check_privilege() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"
  if [[ "$user" == "root" ]]; then
    return 0
  fi

  if ssh_exec "$ip" "$user" "$pass_var" "$key_var" "sudo -n true" &>/dev/null; then
    return 0
  fi

  err "$label 使用非 root 用户 $user，但没有免密 sudo。"
  err "从裸机部署 k3s、Chaos Mesh 和导入镜像需要 root 或免密 sudo。"
  err "请改用 root SSH，或让管理员配置 sudoers 后重试。"
  return 1
}

artifact_urls_for_role() {
  local role="$1"
  local role_cloud base_url base_bundle
  local image_import_mode="${IMAGE_IMPORT_MODE:-local}"
  if [[ "$image_import_mode" == "auto" ]]; then image_import_mode="local"; fi

  if [[ -n "${K3S_INSTALL_URL:-}" ]]; then echo "$K3S_INSTALL_URL"; fi
  if [[ -n "${K3S_BINARY_URL:-}" ]]; then echo "$K3S_BINARY_URL"; fi

  base_bundle="${BASE_IMAGE_BUNDLE_NAME:-k3s-chaos-base-images.tar}"
  if [[ -n "${BASE_IMAGE_ARTIFACT_URL:-}" ]]; then
    echo "$BASE_IMAGE_ARTIFACT_URL"
  elif [[ "$image_import_mode" == "remote" && -n "${IMAGE_ARTIFACT_BASE_URL:-}" ]]; then
    echo "${IMAGE_ARTIFACT_BASE_URL%/}/$base_bundle"
  fi

  if [[ "$image_import_mode" == "remote" && -n "${IMAGE_ARTIFACT_BASE_URL:-}" ]]; then
    base_url="${IMAGE_ARTIFACT_BASE_URL%/}"
    echo "$base_url/common-image-tars.tar.gz"
    for role in $(host_roles_for_ip "$(role_ip "$role")"); do
      role_cloud="$(role_cloud_dir "$role")"
      echo "$base_url/${role_cloud}-image-tars.tar.gz"
    done
  fi
}

check_artifact_downloads() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5" role="$6"
  local urls url sudo_prefix

  urls="$(artifact_urls_for_role "$role" | awk 'NF && !seen[$0]++')"
  [[ -n "$urls" ]] || return 0

  sudo_prefix="$(remote_priv_prefix "$user")"
  log "$label 制品下载预检:"
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    set -e
    if ! command -v curl >/dev/null 2>&1; then
      if command -v apt-get >/dev/null 2>&1; then
        ${sudo_prefix}apt-get update
        ${sudo_prefix}apt-get install -y curl
      else
        echo '缺少 curl，无法做制品下载预检' >&2
        exit 1
      fi
    fi
    while IFS= read -r url; do
      [[ -n \"\$url\" ]] || continue
      echo \"  checking \$url\"
      curl -fsIL --connect-timeout 15 --max-time 60 -o /dev/null \"\$url\"
    done <<'EOF'
$urls
EOF
  "
}

fail=0
for role in $(unique_role_hosts); do
  ip="$(role_ip "$role")"
  user="$(role_user "$role")"
  pass_var="$(role_pass_var "$role")"
  key_var="$(role_key_var "$role")"
  label="$(role_label "$role")"

  check_ssh "$ip" "$user" "$pass_var" "$key_var" "$label" || fail=1
  check_env "$ip" "$user" "$pass_var" "$key_var" "$label" || fail=1
  check_arch "$ip" "$user" "$pass_var" "$key_var" "$label" || fail=1
  check_privilege "$ip" "$user" "$pass_var" "$key_var" "$label" || fail=1
  check_artifact_downloads "$ip" "$user" "$pass_var" "$key_var" "$label" "$role" || fail=1
done

[[ $fail -eq 1 ]] && exit 1

log "服务器检查通过"
