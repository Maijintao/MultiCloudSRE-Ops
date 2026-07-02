#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-injector.yaml}"
kc() { local ctx=$1; shift; kubectl --context="$ctx" -n seat-1 "$@"; }
PID_FILE=/tmp/dns-chaos-payment.pid
LOG_FILE=/tmp/dns-chaos-payment.log

kill_pattern() {
  local pattern=$1
  while read -r pid; do
    [[ -n "${pid:-}" ]] || continue
    kill "$pid" >/dev/null 2>&1 || true
  done < <(pgrep -f "$pattern" || true)
}

force_delete() {
  local ctx=$1 kind=$2 name=$3
  kc "$ctx" patch "$kind" "$name" --type='json' -p='[{"op":"remove","path":"/metadata/finalizers"}]' >/dev/null 2>&1 || true
  kc "$ctx" delete "$kind" "$name" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}

echo "[recover] dns-chaos: 删除所有 DNSChaos 实验"

# 先终止延迟注入后台任务，避免晚到 DNSChaos
if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${pid:-}" ]]; then
    kill "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$PID_FILE"
fi
kill_pattern "dns-chaos-payment"
kill_pattern "$LOG_FILE"

# 立即强制清理已存在的资源（并行）
force_delete tencent dnschaos dns-chaos-productcatalog &
force_delete alicloud dnschaos dns-chaos-recommendation &
force_delete aws dnschaos dns-chaos-payment &
wait

# payment 是延迟注入（T+30s），短窗口兜底，防止恢复后“晚到”
for _ in $(seq 1 40); do
  kill_pattern "dns-chaos-payment"
  kill_pattern "$LOG_FILE"
  force_delete aws dnschaos dns-chaos-payment
  if ! kc aws get dnschaos dns-chaos-payment >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

echo "[recover] 完成"
