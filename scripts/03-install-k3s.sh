#!/bin/bash
# 03 - 安装 k3s（三台并发）

if [[ "${SKIP_K3S_INSTALL:-false}" == "true" ]]; then
  log "SKIP_K3S_INSTALL=true, 跳过 k3s 安装"
  return 0 2>/dev/null || exit 0
fi

log "在三台服务器上安装 k3s..."

install_k3s() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"
  local sudo_prefix
  sudo_prefix="$(remote_priv_prefix "$user")"

  log "  安装 k3s on $label ($ip)..."

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    # 检查是否已安装
    if command -v k3s &>/dev/null; then
      echo 'k3s 已安装: '\$(k3s --version | head -1)
      exit 0
    fi

    # 安装 k3s（禁用 traefik，我们用 NodePort）
    curl -sfL https://get.k3s.io | ${sudo_prefix}env INSTALL_K3S_EXEC='--disable=traefik --write-kubeconfig-mode=644 --tls-san ${ip}' sh -

    # 等待就绪
    sleep 5
    ${sudo_prefix}k3s kubectl get nodes
  "
}

# 三台并发安装
install_k3s "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" "阿里云" &
pid1=$!
install_k3s "$TENCENT_IP" "$TENCENT_USER" "TENCENT_PASS" "TENCENT_KEY" "腾讯云" &
pid2=$!
install_k3s "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" "AWS" &
pid3=$!

fail=0
wait $pid1 || { err "阿里云 k3s 安装失败"; fail=1; }
wait $pid2 || { err "腾讯云 k3s 安装失败"; fail=1; }
wait $pid3 || { err "AWS k3s 安装失败"; fail=1; }

[[ $fail -eq 1 ]] && exit 1

log "k3s 安装完成（三台）"
