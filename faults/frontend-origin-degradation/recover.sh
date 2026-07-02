#!/usr/bin/env bash
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-injector.yaml}"
kc() { local ctx=$1; shift; kubectl --context="$ctx" -n seat-1 "$@"; }

echo "[recover] challenge-37: 删除全部 Chaos 对象"

echo "[1/6] 删除 origin-frontend-delay"
kc alicloud delete networkchaos origin-frontend-delay --ignore-not-found 2>/dev/null || true

echo "[2/6] 删除 origin-frontend-loss"
kc alicloud delete networkchaos origin-frontend-loss --ignore-not-found 2>/dev/null || true

echo "[3/6] 删除 catalog-stale-read-delay"
kc tencent delete networkchaos catalog-stale-read-delay --ignore-not-found 2>/dev/null || true

echo "[4/6] 删除 recommend-cache-miss-delay"
kc alicloud delete networkchaos recommend-cache-miss-delay --ignore-not-found 2>/dev/null || true

echo "[5/6] 删除 checkout-db-connection-jitter"
kc alicloud delete networkchaos checkout-db-connection-jitter --ignore-not-found 2>/dev/null || true

echo "[6/6] 删除 alicloud-node-cpu-pressure"
kc alicloud delete stresschaos alicloud-node-cpu-pressure --ignore-not-found 2>/dev/null || true

kc alicloud rollout status deploy/frontend --timeout=120s 2>/dev/null || true

echo "[recover] complete."
