#!/bin/bash
# 08 - 生成三云访问凭据（readonly/injector kubeconfig + Chaos Dashboard token）

if [[ "${SKIP_ACCESS_GENERATION:-false}" == "true" ]]; then
  log "SKIP_ACCESS_GENERATION=true, 跳过访问凭据生成"
  return 0 2>/dev/null || exit 0
fi

GENERATED_DIR="$SCRIPT_DIR/kubeconfigs/generated"
mkdir -p "$GENERATED_DIR"
chmod 700 "$GENERATED_DIR"

merge_backup_done=0

merge_local_kubeconfig() {
  local src="$1"
  local dst="${LOCAL_KUBECONFIG:-$HOME/.kube/config}"
  local tmp

  mkdir -p "$(dirname "$dst")"
  if [[ ! -f "$dst" ]]; then
    cat > "$dst" <<'EOF'
apiVersion: v1
kind: Config
preferences: {}
clusters: []
users: []
contexts: []
current-context: ""
EOF
    chmod 600 "$dst"
  fi

  if [[ $merge_backup_done -eq 0 ]]; then
    cp "$dst" "${dst}.bak.$(date +%Y%m%d%H%M%S)"
    merge_backup_done=1
  fi

  tmp="$(mktemp)"
  KUBECONFIG="$dst:$src" kubectl config view --flatten > "$tmp"
  mv "$tmp" "$dst"
  chmod 600 "$dst"
}

generate_for() {
  local cloud="$1" ip="$2" user="$3" pass_var="$4" key_var="$5" label="$6"
  local remote_script="/tmp/sre-remote-generate-access.sh"

  log "  生成 $label 访问凭据..."

  scp_upload "$SCRIPT_DIR/kubeconfigs/templates/readonly-clusterrole.yaml" \
    "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-readonly.yaml"
  scp_upload "$SCRIPT_DIR/kubeconfigs/templates/injector-clusterrole.yaml" \
    "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-injector.yaml"
  scp_upload "$SCRIPT_DIR/kubeconfigs/templates/chaos-dashboard-clusterrole.yaml" \
    "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-chaos-dashboard.yaml"
  scp_upload "$SCRIPT_DIR/scripts/remote-generate-access.sh" \
    "$ip" "$user" "$pass_var" "$key_var" "$remote_script"

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "chmod +x $remote_script && $remote_script '$cloud' '$ip'"

  scp_download "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-access/${cloud}-readonly.kubeconfig" \
    "$GENERATED_DIR/${cloud}-readonly.kubeconfig"
  scp_download "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-access/${cloud}-injector.kubeconfig" \
    "$GENERATED_DIR/${cloud}-injector.kubeconfig"
  scp_download "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-access/${cloud}-chaos-dashboard.token" \
    "$GENERATED_DIR/${cloud}-chaos-dashboard.token"

  chmod 600 "$GENERATED_DIR/${cloud}-readonly.kubeconfig" \
    "$GENERATED_DIR/${cloud}-injector.kubeconfig" \
    "$GENERATED_DIR/${cloud}-chaos-dashboard.token"

  if [[ "${UPDATE_LOCAL_KUBECONFIG:-true}" == "true" ]]; then
    merge_local_kubeconfig "$GENERATED_DIR/${cloud}-readonly.kubeconfig"
    merge_local_kubeconfig "$GENERATED_DIR/${cloud}-injector.kubeconfig"
  fi

  log "  $label 访问凭据已生成"
}

log "生成三云 kubeconfig 和 Chaos Dashboard token..."

generate_for "aliyun" "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" "阿里云"
generate_for "tencent" "$TENCENT_IP" "$TENCENT_USER" "TENCENT_PASS" "TENCENT_KEY" "腾讯云"
generate_for "aws" "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" "AWS"

if [[ "${UPDATE_LOCAL_KUBECONFIG:-true}" == "true" ]]; then
  log "本机 kubeconfig 已合并上下文：sre-aliyun-*, sre-tencent-*, sre-aws-*"
else
  log "已跳过合并本机 kubeconfig，可直接使用 kubeconfigs/generated/*.kubeconfig"
fi

log "访问凭据生成完成 → kubeconfigs/generated/"
