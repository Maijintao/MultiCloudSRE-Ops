#!/bin/bash
# 04 - 安装 Chaos Mesh（按唯一服务器并发）

if [[ "${SKIP_CHAOS_MESH:-false}" == "true" ]]; then
  log "SKIP_CHAOS_MESH=true, 跳过 Chaos Mesh 安装"
  return 0 2>/dev/null || exit 0
fi

log "在服务器上安装 Chaos Mesh..."

install_chaos_mesh() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"
  local sudo_prefix
  sudo_prefix="$(remote_priv_prefix "$user")"

  log "  安装 Chaos Mesh on $label ($ip)..."

  # 上传 helm values 文件
  scp_upload "$SCRIPT_DIR/manifests/chaos-mesh/values.yaml" "$ip" "$user" "$pass_var" "$key_var" "/tmp/chaos-mesh-values.yaml"

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    # 检查是否已安装
    if ${sudo_prefix}k3s kubectl get ns chaos-mesh &>/dev/null; then
      echo 'Chaos Mesh 已安装'
      ${sudo_prefix}k3s kubectl get pods -n chaos-mesh
      exit 0
    fi

    # 安装 helm（如果没有）
    if ! command -v helm &>/dev/null; then
      curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 -o /tmp/get-helm-3.sh
      if [[ -s /tmp/get-helm-3.sh ]]; then
        ${sudo_prefix}bash /tmp/get-helm-3.sh
        rm -f /tmp/get-helm-3.sh
      else
        echo "ERROR: Failed to download helm install script" >&2
        # continue anyway as helm might already be installed
      fi
    fi

    # 添加 chaos-mesh repo
    ${sudo_prefix}helm repo add chaos-mesh https://charts.chaos-mesh.org 2>/dev/null || true
    ${sudo_prefix}helm repo update

    # 安装
    ${sudo_prefix}helm install chaos-mesh chaos-mesh/chaos-mesh \
      -n chaos-mesh \
      --create-namespace \
      --kubeconfig /etc/rancher/k3s/k3s.yaml \
      -f /tmp/chaos-mesh-values.yaml

    # 等待就绪
    sleep 10
    ${sudo_prefix}k3s kubectl wait --for=condition=Ready pods --all -n chaos-mesh --timeout=120s
  "
}

fail=0
pids=()
labels=()
for role in $(unique_role_hosts); do
  install_chaos_mesh \
    "$(role_ip "$role")" \
    "$(role_user "$role")" \
    "$(role_pass_var "$role")" \
    "$(role_key_var "$role")" \
    "$(role_label "$role")" &
  pids+=("$!")
  labels+=("$(role_label "$role")")
done

for i in "${!pids[@]}"; do
  wait "${pids[$i]}" || { err "${labels[$i]} Chaos Mesh 安装失败"; fail=1; }
done

[[ $fail -eq 1 ]] && exit 1

log "Chaos Mesh 安装完成"
