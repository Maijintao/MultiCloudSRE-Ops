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

echo "[inject] cross-cloud-latency-overlap: 双重故障注入开始"

echo "[1/2] NetworkChaos: checkoutservice 网络延迟 1500ms (阿里云)"
kc alicloud apply -f - <<'EOF'
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: cross-cloud-checkout-network-delay
  namespace: seat-1
spec:
  action: delay
  mode: one
  selector:
    namespaces: [seat-1]
    labelSelectors:
      app: checkoutservice
  delay:
    latency: "1500ms"
    correlation: "70"
    jitter: "300ms"
  direction: to
  duration: "15m"
EOF

echo "[2/2] productcatalogservice: EXTRA_LATENCY 改为 1800ms (腾讯云)"
kc tencent set env deploy/productcatalogservice EXTRA_LATENCY=1800ms --overwrite

echo "[inject] 所有故障已注入，持续到恢复"
echo "[inject] checkoutservice: 网络延迟 → 结账响应变慢"
echo "[inject] productcatalogservice: EXTRA_LATENCY=1800ms → 商品查询偶尔卡顿"
echo "[inject] 两个故障分布在不同云，需要跨云排查"
