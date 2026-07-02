#!/usr/bin/env bash
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-injector.yaml}"
kc() { local ctx=$1; shift; kubectl --context="$ctx" -n seat-1 "$@"; }

echo "[recover] challenge-31: 删除 Chaos 对象 + 恢复 env"

# 并行删除所有 chaos + 恢复 env
kc tencent delete networkchaos gw-to-aws-order-delay --ignore-not-found &
kc tencent delete networkchaos gw-to-aws-order-loss --ignore-not-found &
kc tencent delete stresschaos tencent-global-cpu-stress --ignore-not-found &
kc tencent set env deploy/new-gatewayservice UPSTREAM_TIMEOUT- MAX_RETRIES- 2>/dev/null &

wait

kc tencent rollout status deploy/new-gatewayservice --timeout=120s || true

echo "[recover] complete."
