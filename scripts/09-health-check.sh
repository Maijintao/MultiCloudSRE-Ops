#!/bin/bash
# 09 - 端到端健康检查（跨云链路验证）

log "执行端到端健康检查..."

fail_count=0

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
for cloud in aliyun tencent aws; do
  log "  $cloud:"
  kubectl_for "$cloud" "get pods -n seat-1 --no-headers 2>/dev/null | head -20" || true
done

log ""
log "── 跨云链路验证 ──"

# 阿里云 → 腾讯云
check_tcp "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" \
  "$TENCENT_IP" "30008" "阿里云→腾讯 productcatalog"
check_tcp "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" \
  "$TENCENT_IP" "30007" "阿里云→腾讯 cart"
check_tcp "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" \
  "$TENCENT_IP" "30009" "阿里云→腾讯 currency"

# 阿里云 → AWS
check_tcp "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" \
  "$AWS_IP" "30051" "阿里云→AWS payment"
check_tcp "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" \
  "$AWS_IP" "30070" "阿里云→AWS orders"

# 腾讯云 → AWS
check_tcp "$TENCENT_IP" "$TENCENT_USER" "TENCENT_PASS" "TENCENT_KEY" \
  "$AWS_IP" "30070" "腾讯云→AWS orders"

# AWS → 腾讯云
check_tcp "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" \
  "$TENCENT_IP" "30008" "AWS→腾讯 productcatalog"

# AWS → 阿里云
check_tcp "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" \
  "$ALIYUN_IP" "30051" "AWS→阿里 shipping"

# 前端可访问性
log ""
log "── 前端访问 ──"
local_code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 35 "http://${ALIYUN_IP}:31366" 2>/dev/null || echo "000")
if [[ "$local_code" == "200" ]]; then
  log "  [OK] 前端 http://${ALIYUN_IP}:31366 → HTTP $local_code"
else
  err "  [FAIL] 前端 http://${ALIYUN_IP}:31366 → HTTP $local_code"
  fail_count=$((fail_count + 1))
fi

log ""
log "── 本地访问凭据验证 ──"
GEN_DIR="$SCRIPT_DIR/kubeconfigs/generated"
for cloud in aliyun tencent aws; do
  check_local_kubeconfig "$GEN_DIR/${cloud}-readonly.kubeconfig" "list" "pods" "seat-1" "$cloud readonly kubeconfig"
  check_local_kubeconfig "$GEN_DIR/${cloud}-injector.kubeconfig" "create" "podchaos.chaos-mesh.org" "seat-1" "$cloud injector kubeconfig"
  check_token_file "$GEN_DIR/${cloud}-chaos-dashboard.token" "$cloud Chaos Dashboard"
done

echo ""
if [[ $fail_count -eq 0 ]]; then
  log "所有健康检查通过！"
else
  err "$fail_count 项检查失败，请检查安全组、6443 API 端口和跨云网络配置"
  exit 1
fi
