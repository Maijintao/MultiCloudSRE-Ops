#!/bin/bash
# 09 - 端到端健康检查（角色链路验证）

log "执行端到端健康检查..."

fail_count=0
PAYMENT_SERVICE_NODEPORT="${PAYMENT_SERVICE_NODEPORT:-30051}"
if [[ "$SERVER1_IP" == "$SERVER3_IP" && "$PAYMENT_SERVICE_NODEPORT" == "30051" ]]; then
  PAYMENT_SERVICE_NODEPORT="30075"
fi

check_tcp() {
  local from_ip="$1" from_user="$2" from_pass_var="$3" from_key_var="$4"
  local target_host="$5" target_port="$6" label="$7"

  if ssh_exec "$from_ip" "$from_user" "$from_pass_var" "$from_key_var" \
    "timeout 8 bash -c '</dev/tcp/${target_host}/${target_port}'" &>/dev/null; then
    log "  [OK] $label → TCP ${target_host}:${target_port}"
  else
    err "  [FAIL] $label → TCP ${target_host}:${target_port}"
    fail_count=$((fail_count + 1))
  fi
}

check_local_kubeconfig() {
  local kubeconfig="$1"
  local verb="$2"
  local resource="$3"
  local namespace="$4"
  local label="$5"

  if [[ ! -s "$kubeconfig" ]]; then
    err "  [FAIL] $label → 文件不存在或为空: $kubeconfig"
    fail_count=$((fail_count + 1))
    return
  fi

  local answer
  answer=$(kubectl --kubeconfig "$kubeconfig" auth can-i "$verb" "$resource" -n "$namespace" 2>/dev/null | tail -n 1 || true)
  if [[ "$answer" == "yes" ]]; then
    log "  [OK] $label → can-i $verb $resource"
  else
    err "  [FAIL] $label → can-i $verb $resource = ${answer:-error}"
    fail_count=$((fail_count + 1))
  fi
}

check_token_file() {
  local token_file="$1"
  local label="$2"

  if [[ -s "$token_file" ]]; then
    log "  [OK] $label → token 已生成"
  else
    err "  [FAIL] $label → token 文件不存在或为空: $token_file"
    fail_count=$((fail_count + 1))
  fi
}

log "── Pod 状态 ──"
for role in server1 server2 server3; do
  log "  $(role_label "$role"):"
  kubectl_for "$role" "get pods -n seat-1 --no-headers 2>/dev/null | head -20" || true
done

log ""
log "── 跨云链路验证 ──"

# 服务器1 → 服务器2
check_tcp "$SERVER1_IP" "$SERVER1_USER" "SERVER1_PASS" "SERVER1_KEY" \
  "$SERVER2_IP" "30008" "服务器1→服务器2 productcatalog"
check_tcp "$SERVER1_IP" "$SERVER1_USER" "SERVER1_PASS" "SERVER1_KEY" \
  "$SERVER2_IP" "30007" "服务器1→服务器2 cart"
check_tcp "$SERVER1_IP" "$SERVER1_USER" "SERVER1_PASS" "SERVER1_KEY" \
  "$SERVER2_IP" "30009" "服务器1→服务器2 currency"

# 服务器1 → 服务器3
check_tcp "$SERVER1_IP" "$SERVER1_USER" "SERVER1_PASS" "SERVER1_KEY" \
  "$SERVER3_IP" "$PAYMENT_SERVICE_NODEPORT" "服务器1→服务器3 payment"
check_tcp "$SERVER1_IP" "$SERVER1_USER" "SERVER1_PASS" "SERVER1_KEY" \
  "$SERVER3_IP" "30070" "服务器1→服务器3 orders"

# 服务器2 → 服务器3
check_tcp "$SERVER2_IP" "$SERVER2_USER" "SERVER2_PASS" "SERVER2_KEY" \
  "$SERVER3_IP" "30070" "服务器2→服务器3 orders"

# 服务器3 → 服务器2
check_tcp "$SERVER3_IP" "$SERVER3_USER" "SERVER3_PASS" "SERVER3_KEY" \
  "$SERVER2_IP" "30008" "服务器3→服务器2 productcatalog"

# 服务器3 → 服务器1
check_tcp "$SERVER3_IP" "$SERVER3_USER" "SERVER3_PASS" "SERVER3_KEY" \
  "$SERVER1_IP" "30051" "服务器3→服务器1 shipping"

# 前端可访问性
log ""
log "── 前端访问 ──"
local_code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 35 "http://${SERVER1_IP}:31366" 2>/dev/null || echo "000")
if [[ "$local_code" == "200" ]]; then
  log "  [OK] 前端 http://${SERVER1_IP}:31366 → HTTP $local_code"
else
  err "  [FAIL] 前端 http://${SERVER1_IP}:31366 → HTTP $local_code"
  fail_count=$((fail_count + 1))
fi

log ""
log "── 本地访问凭据验证 ──"
GEN_DIR="$SCRIPT_DIR/kubeconfigs/generated"
for role in server1 server2 server3; do
  check_local_kubeconfig "$GEN_DIR/${role}-readonly.kubeconfig" "list" "pods" "seat-1" "$role readonly kubeconfig"
  check_local_kubeconfig "$GEN_DIR/${role}-injector.kubeconfig" "create" "podchaos.chaos-mesh.org" "seat-1" "$role injector kubeconfig"
  check_token_file "$GEN_DIR/${role}-chaos-dashboard.token" "$role Chaos Dashboard"
done
check_local_kubeconfig "$GEN_DIR/config-readonly.yaml" "list" "pods" "seat-1" "OJ config-readonly.yaml"
check_local_kubeconfig "$GEN_DIR/config-injector.yaml" "create" "podchaos.chaos-mesh.org" "seat-1" "OJ config-injector.yaml"

echo ""
if [[ $fail_count -eq 0 ]]; then
  log "所有健康检查通过！"
else
  err "$fail_count 项检查失败，请检查安全组、6443 API 端口和跨云网络配置"
  exit 1
fi
