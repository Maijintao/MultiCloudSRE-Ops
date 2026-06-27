#!/bin/bash
# 09 - 端到端健康检查（跨云链路验证）

log "执行端到端健康检查..."

fail_count=0

check_link() {
  local from_ip="$1" from_user="$2" from_pass_var="$3" from_key_var="$4"
  local target_url="$5" label="$6" expected_code="${7:-200}"

  local code
  code=$(ssh_exec "$from_ip" "$from_user" "$from_pass_var" "$from_key_var" \
    "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 10 '$target_url'" 2>/dev/null || echo "000")

  if [[ "$code" == "$expected_code" ]]; then
    log "  [OK] $label → HTTP $code"
  else
    err "  [FAIL] $label → HTTP $code (期望 $expected_code)"
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
check_link "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" \
  "http://${TENCENT_IP}:30008" "阿里云→腾讯 productcatalog"
check_link "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" \
  "http://${TENCENT_IP}:30007" "阿里云→腾讯 cart"
check_link "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" \
  "http://${TENCENT_IP}:30009" "阿里云→腾讯 currency"

# 阿里云 → AWS
check_link "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" \
  "http://${AWS_IP}:30051" "阿里云→AWS payment"
check_link "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" \
  "http://${AWS_IP}:30070" "阿里云→AWS orders"

# 腾讯云 → AWS
check_link "$TENCENT_IP" "$TENCENT_USER" "TENCENT_PASS" "TENCENT_KEY" \
  "http://${AWS_IP}:30070" "腾讯云→AWS orders"

# AWS → 腾讯云
check_link "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" \
  "http://${TENCENT_IP}:30008" "AWS→腾讯 productcatalog"

# AWS → 阿里云
check_link "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" \
  "http://${ALIYUN_IP}:30051" "AWS→阿里 shipping"

# 前端可访问性
log ""
log "── 前端访问 ──"
local_code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 10 "http://${ALIYUN_IP}:31366" 2>/dev/null || echo "000")
if [[ "$local_code" == "200" ]]; then
  log "  [OK] 前端 http://${ALIYUN_IP}:31366 → HTTP $local_code"
else
  warn "  [WARN] 前端 http://${ALIYUN_IP}:31366 → HTTP $local_code"
fi

echo ""
if [[ $fail_count -eq 0 ]]; then
  log "所有健康检查通过！"
else
  warn "$fail_count 项检查失败，请检查安全组和网络配置"
fi
