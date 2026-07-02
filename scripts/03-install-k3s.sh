#!/bin/bash
# 03 - 安装 k3s（按唯一服务器并发）

if [[ "${SKIP_K3S_INSTALL:-false}" == "true" ]]; then
  log "SKIP_K3S_INSTALL=true, 跳过 k3s 安装"
  return 0 2>/dev/null || exit 0
fi

log "在服务器上安装 k3s..."

install_k3s() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"
  local sudo_prefix uploaded_binary=0
  sudo_prefix="$(remote_priv_prefix "$user")"

  log "  安装 k3s on $label ($ip)..."

  if [[ -n "${K3S_BINARY_PATH:-}" ]]; then
    if [[ ! -f "$K3S_BINARY_PATH" ]]; then
      err "K3S_BINARY_PATH 不存在: $K3S_BINARY_PATH"
      return 1
    fi

    if ssh_exec "$ip" "$user" "$pass_var" "$key_var" "command -v k3s >/dev/null 2>&1"; then
      ssh_exec "$ip" "$user" "$pass_var" "$key_var" "k3s --version | head -1"
      return 0
    fi

    log "    上传本地 k3s 二进制: $K3S_BINARY_PATH"
    scp_upload "$K3S_BINARY_PATH" "$ip" "$user" "$pass_var" "$key_var" "/tmp/k3s"
    uploaded_binary=1
  fi

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    set -e
    # 检查是否已安装
    if command -v k3s &>/dev/null; then
      echo 'k3s 已安装: '\$(k3s --version | head -1)
      exit 0
    fi

    install_url='${K3S_INSTALL_URL:-https://get.k3s.io}'
    k3s_binary_url='${K3S_BINARY_URL:-}'
    uploaded_binary='${uploaded_binary}'

    if [[ \"\$uploaded_binary\" == '1' && -s /tmp/k3s ]]; then
      echo '使用已上传的 k3s 二进制: /tmp/k3s'
      ${sudo_prefix}install -m 0755 /tmp/k3s /usr/local/bin/k3s
      rm -f /tmp/k3s
      curl -sfL --retry 5 --retry-delay 5 \"\$install_url\" | ${sudo_prefix}env \
        INSTALL_K3S_SKIP_DOWNLOAD=true \
        INSTALL_K3S_EXEC='--disable=traefik --write-kubeconfig-mode=644 --tls-san ${ip}' \
        sh -
    elif [[ -n \"\$k3s_binary_url\" ]]; then
      echo \"从制品 URL 下载 k3s: \$k3s_binary_url\"
      rm -f /tmp/k3s /tmp/k3s.aria2
      if ! command -v aria2c >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
        ${sudo_prefix}apt-get update
        ${sudo_prefix}apt-get install -y aria2 || true
      fi
      if command -v aria2c >/dev/null 2>&1; then
        aria2c -x 8 -s 8 -k 1M --retry-wait=5 --max-tries=5 \
          --connect-timeout=20 --timeout=60 \
          -d /tmp -o k3s \"\$k3s_binary_url\"
      else
        curl -fL --retry 5 --retry-delay 5 --connect-timeout 20 --max-time 600 \
          -o /tmp/k3s \"\$k3s_binary_url\"
      fi
      ${sudo_prefix}install -m 0755 /tmp/k3s /usr/local/bin/k3s
      rm -f /tmp/k3s
      curl -sfL --retry 5 --retry-delay 5 \"\$install_url\" | ${sudo_prefix}env \
        INSTALL_K3S_SKIP_DOWNLOAD=true \
        INSTALL_K3S_EXEC='--disable=traefik --write-kubeconfig-mode=644 --tls-san ${ip}' \
        sh -
    else
      # 安装 k3s（禁用 traefik，我们用 NodePort）
      curl -sfL --retry 5 --retry-delay 5 \"\$install_url\" | ${sudo_prefix}env \
        INSTALL_K3S_EXEC='--disable=traefik --write-kubeconfig-mode=644 --tls-san ${ip}' \
        sh -
    fi

    # 等待就绪
    sleep 5
    ${sudo_prefix}k3s kubectl get nodes
  "
}

fail=0
pids=()
labels=()
for role in $(unique_role_hosts); do
  install_k3s \
    "$(role_ip "$role")" \
    "$(role_user "$role")" \
    "$(role_pass_var "$role")" \
    "$(role_key_var "$role")" \
    "$(role_label "$role")" &
  pids+=("$!")
  labels+=("$(role_label "$role")")
done

for i in "${!pids[@]}"; do
  wait "${pids[$i]}" || { err "${labels[$i]} k3s 安装失败"; fail=1; }
done

[[ $fail -eq 1 ]] && exit 1

log "k3s 安装完成"
