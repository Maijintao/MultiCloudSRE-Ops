#!/bin/bash
# 08 - 生成服务器角色访问凭据（readonly/injector kubeconfig + Chaos Dashboard token）

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

add_context_alias() {
  local kubeconfig="$1"
  local source_context="$2"
  local alias_context="$3"

  local cluster user namespace
  cluster="$(kubectl --kubeconfig "$kubeconfig" config view -o "jsonpath={.contexts[?(@.name==\"$source_context\")].context.cluster}")"
  user="$(kubectl --kubeconfig "$kubeconfig" config view -o "jsonpath={.contexts[?(@.name==\"$source_context\")].context.user}")"
  namespace="$(kubectl --kubeconfig "$kubeconfig" config view -o "jsonpath={.contexts[?(@.name==\"$source_context\")].context.namespace}")"
  [[ -n "$cluster" && -n "$user" ]] || return 1
  kubectl --kubeconfig "$kubeconfig" config set-context "$alias_context" \
    --cluster="$cluster" \
    --user="$user" \
    --namespace="${namespace:-seat-1}" >/dev/null
}

build_combined_kubeconfig() {
  local kind="$1"
  local output="$2"
  local files=()
  local role source_context

  for role in server1 server2 server3; do
    files+=("$GENERATED_DIR/${role}-${kind}.kubeconfig")
  done

  KUBECONFIG="$(IFS=:; echo "${files[*]}")" kubectl config view --flatten > "$output"

  for role in server1 server2 server3; do
    source_context="sre-${role}-${kind}"
    add_context_alias "$output" "$source_context" "$role"
  done

  # 兼容已有 OJ demo/fault 脚本和 MCP 默认 context 名。
  add_context_alias "$output" "sre-server1-${kind}" "alicloud"
  add_context_alias "$output" "sre-server2-${kind}" "tencent"
  add_context_alias "$output" "sre-server3-${kind}" "aws"

  kubectl --kubeconfig "$output" config use-context server1 >/dev/null
  chmod 600 "$output"
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

log "生成服务器角色 kubeconfig 和 Chaos Dashboard token..."

# 按唯一 IP 去重，避免同 IP 重复生成（如 server1 和 server2 共享 IP）
# 兼容 bash 3.x，不用 declare -A
generated_ips=""
for role in server1 server2 server3; do
  ip="$(role_ip "$role")"
  # 精确匹配 IP（避免子串误匹配，如 10.0.0.1 匹配 10.0.0.10）
  prev_role=""
  already=0
  for seen in $generated_ips; do
    [[ "$seen" == "$ip" ]] && already=1 && break
  done
  if [[ $already -eq 1 ]]; then
    # 找到之前生成过的同 IP 角色
    for r in server1 server2 server3; do
      rip="$(role_ip "$r")"
      if [[ "$rip" == "$ip" && "$r" != "$role" ]]; then
        if [[ -f "$GENERATED_DIR/${r}-readonly.kubeconfig" ]]; then
          prev_role="$r"
          break
        fi
      fi
    done
  fi

  if [[ -n "$prev_role" ]]; then
    log "  $role 与 $prev_role 共享 IP ($ip)，复用凭据..."
    for suffix in readonly.kubeconfig injector.kubeconfig chaos-dashboard.token; do
      cp "$GENERATED_DIR/${prev_role}-${suffix}" "$GENERATED_DIR/${role}-${suffix}"
    done
    chmod 600 "$GENERATED_DIR/${role}-readonly.kubeconfig" \
      "$GENERATED_DIR/${role}-injector.kubeconfig" \
      "$GENERATED_DIR/${role}-chaos-dashboard.token"

    if [[ "${UPDATE_LOCAL_KUBECONFIG:-true}" == "true" ]]; then
      merge_local_kubeconfig "$GENERATED_DIR/${role}-readonly.kubeconfig"
      merge_local_kubeconfig "$GENERATED_DIR/${role}-injector.kubeconfig"
    fi
  else
    generate_for \
      "$role" \
      "$ip" \
      "$(role_user "$role")" \
      "$(role_pass_var "$role")" \
      "$(role_key_var "$role")" \
      "$(role_label "$role")"
    generated_ips="$generated_ips $ip"
  fi
done

build_combined_kubeconfig "readonly" "$GENERATED_DIR/config-readonly.yaml"
build_combined_kubeconfig "injector" "$GENERATED_DIR/config-injector.yaml"

if [[ "${UPDATE_LOCAL_KUBECONFIG:-true}" == "true" ]]; then
  log "本机 kubeconfig 已合并上下文：sre-server1-*, sre-server2-*, sre-server3-*"
else
  log "已跳过合并本机 kubeconfig，可直接使用 kubeconfigs/generated/*.kubeconfig"
fi

log "访问凭据生成完成 → kubeconfigs/generated/"
log "  OJ readonly: $GENERATED_DIR/config-readonly.yaml"
log "  OJ injector: $GENERATED_DIR/config-injector.yaml"
