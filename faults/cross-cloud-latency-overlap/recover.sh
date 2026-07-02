#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${KUBECONFIG:-}" ]]; then
  if [[ -f "$HOME/.kube/config-competition" ]]; then
    export KUBECONFIG="$HOME/.kube/config-competition"
  else
    export KUBECONFIG="$HOME/.kube/config-injector.yaml"
  fi
fi
kc() { kubectl --context="$1" -n seat-1 "${@:2}"; }

force_delete() {
  local ctx=$1 kind=$2 name=$3
  kubectl --context="$ctx" -n seat-1 delete "$kind" "$name" --ignore-not-found --wait=false 2>/dev/null || true
  kubectl --context="$ctx" -n seat-1 patch "$kind" "$name" --type=merge -p '{"metadata":{"finalizers":[]}}' 2>/dev/null || true
}

echo "[recover] cross-cloud-latency-overlap: 开始恢复"

echo "[1/2] 删除 checkoutservice NetworkChaos (阿里云)"
force_delete alicloud networkchaos cross-cloud-checkout-network-delay

echo "[2/2] 移除 productcatalogservice 的 EXTRA_LATENCY (腾讯云)"
kc tencent set env deploy/productcatalogservice EXTRA_LATENCY- --overwrite

echo "[recover] 所有故障已恢复"
