#!/bin/bash
# 04 - 安装 Chaos Mesh（按唯一服务器并发）
# 本地下载 helm + chart，SCP 到服务器安装，避免服务器直连外网

if [[ "${SKIP_CHAOS_MESH:-false}" == "true" ]]; then
  log "SKIP_CHAOS_MESH=true, 跳过 Chaos Mesh 安装"
  return 0 2>/dev/null || exit 0
fi

log "在服务器上安装 Chaos Mesh..."

DIST_DIR="$SCRIPT_DIR/dist"
HELM_BINARY="$DIST_DIR/helm"
HELM_VERSION="v3.16.4"
CHART_CACHE="$DIST_DIR/chaos-mesh-chart.tgz"

# --- 本地准备 helm 二进制 ---
if [[ ! -x "$HELM_BINARY" ]]; then
  log "  下载 helm ${HELM_VERSION} 到本地..."
  mkdir -p "$DIST_DIR"
  curl --http1.1 -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" \
    -o "$DIST_DIR/helm.tar.gz"
  tar -xzf "$DIST_DIR/helm.tar.gz" -C "$DIST_DIR"
  mv "$DIST_DIR/linux-amd64/helm" "$HELM_BINARY"
  chmod +x "$HELM_BINARY"
  rm -rf "$DIST_DIR/helm.tar.gz" "$DIST_DIR/linux-amd64"
  log "  helm 就绪: $($HELM_BINARY version --short 2>/dev/null)"
fi

# --- 本地下载 chaos-mesh chart ---
if [[ ! -f "$CHART_CACHE" ]]; then
  log "  下载 chaos-mesh Helm chart 到本地..."
  $HELM_BINARY repo add chaos-mesh https://charts.chaos-mesh.org 2>/dev/null || true
  $HELM_BINARY repo update
  $HELM_BINARY pull chaos-mesh/chaos-mesh --destination "$DIST_DIR"
  # pull 下来的文件名可能是 chaos-mesh-X.Y.Z.tgz
  local_chart="$(ls -t "$DIST_DIR"/chaos-mesh-*.tgz 2>/dev/null | head -1)"
  if [[ -n "$local_chart" && "$local_chart" != "$CHART_CACHE" ]]; then
    mv "$local_chart" "$CHART_CACHE"
  fi
  if [[ ! -f "$CHART_CACHE" ]]; then
    err "无法下载 chaos-mesh chart"
    exit 1
  fi
  log "  chart 就绪: $CHART_CACHE"
fi

install_chaos_mesh() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"
  local sudo_prefix
  sudo_prefix="$(remote_priv_prefix "$user")"

  log "  安装 Chaos Mesh on $label ($ip)..."

  # 检查是否已安装
  if ssh_exec "$ip" "$user" "$pass_var" "$key_var" "${sudo_prefix}k3s kubectl get ns chaos-mesh &>/dev/null" && \
     ssh_exec "$ip" "$user" "$pass_var" "$key_var" "${sudo_prefix}k3s kubectl get pods -n chaos-mesh --no-headers 2>/dev/null | head -1 | grep -q ."; then
    log "  $label Chaos Mesh 已安装"
    ssh_exec "$ip" "$user" "$pass_var" "$key_var" "${sudo_prefix}k3s kubectl get pods -n chaos-mesh"
    return 0
  fi

  # 上传 helm + chart + values
  scp_upload "$HELM_BINARY" "$ip" "$user" "$pass_var" "$key_var" "/usr/local/bin/helm"
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "${sudo_prefix}chmod +x /usr/local/bin/helm"
  scp_upload "$CHART_CACHE" "$ip" "$user" "$pass_var" "$key_var" "/tmp/chaos-mesh.tgz"
  scp_upload "$SCRIPT_DIR/manifests/chaos-mesh/values.yaml" "$ip" "$user" "$pass_var" "$key_var" "/tmp/chaos-mesh-values.yaml"

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    set -e
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

    helm install chaos-mesh /tmp/chaos-mesh.tgz \
      -n chaos-mesh \
      --create-namespace \
      -f /tmp/chaos-mesh-values.yaml

    sleep 10
    k3s kubectl wait --for=condition=Ready pods --all -n chaos-mesh --timeout=180s

    rm -f /tmp/chaos-mesh.tgz /tmp/chaos-mesh-values.yaml
  "

  log "  $label Chaos Mesh 安装完成"
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
