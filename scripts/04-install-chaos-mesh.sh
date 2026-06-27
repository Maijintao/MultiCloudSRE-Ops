#!/bin/bash
# 04 - 安装 Chaos Mesh（三台并发）

if [[ "${SKIP_CHAOS_MESH:-false}" == "true" ]]; then
  log "SKIP_CHAOS_MESH=true, 跳过 Chaos Mesh 安装"
  return 0 2>/dev/null || exit 0
fi

log "在三台服务器上安装 Chaos Mesh..."

install_chaos_mesh() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"
  log "  安装 Chaos Mesh on $label ($ip)..."

  # 上传 helm values 文件
  scp_upload "$SCRIPT_DIR/../manifests/chaos-mesh/values.yaml" "$ip" "$user" "$pass_var" "$key_var" "/tmp/chaos-mesh-values.yaml"

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    # 检查是否已安装
    if k3s kubectl get ns chaos-mesh &>/dev/null; then
      echo 'Chaos Mesh 已安装'
      k3s kubectl get pods -n chaos-mesh
      exit 0
    fi

    # 安装 helm（如果没有）
    if ! command -v helm &>/dev/null; then
      curl -sfL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
    fi

    # 添加 chaos-mesh repo
    helm repo add chaos-mesh https://charts.chaos-mesh.org 2>/dev/null || true
    helm repo update

    # 安装
    helm install chaos-mesh chaos-mesh/chaos-mesh \
      -n chaos-mesh \
      --create-namespace \
      -f /tmp/chaos-mesh-values.yaml

    # 等待就绪
    sleep 10
    k3s kubectl wait --for=condition=Ready pods --all -n chaos-mesh --timeout=120s
  "
}

# 三台并发
install_chaos_mesh "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" "阿里云" &
pid1=$!
install_chaos_mesh "$TENCENT_IP" "$TENCENT_USER" "TENCENT_PASS" "TENCENT_KEY" "腾讯云" &
pid2=$!
install_chaos_mesh "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" "AWS" &
pid3=$!

fail=0
wait $pid1 || { err "阿里云 Chaos Mesh 安装失败"; fail=1; }
wait $pid2 || { err "腾讯云 Chaos Mesh 安装失败"; fail=1; }
wait $pid3 || { err "AWS Chaos Mesh 安装失败"; fail=1; }

[[ $fail -eq 1 ]] && exit 1

log "Chaos Mesh 安装完成（三台）"
