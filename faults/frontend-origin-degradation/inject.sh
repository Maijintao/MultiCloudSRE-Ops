#!/usr/bin/env bash
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-injector.yaml}"
kc() { local ctx=$1; shift; kubectl --context="$ctx" -n seat-1 "$@"; }
kc_apply() { local ctx=$1; shift; kc "$ctx" apply -f - "$@"; }

echo "[inject] challenge-37: 前端网络延迟和丢包（6 chaos）"

echo "[1/6] NetworkChaos: frontend 延迟 600ms（根因）"
kc_apply alicloud <<'EOF'
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: origin-frontend-delay
  namespace: seat-1
spec:
  action: delay
  mode: one
  selector:
    namespaces: [seat-1]
    labelSelectors:
      app: frontend
  delay:
    latency: "600ms"
    correlation: "75"
    jitter: "200ms"
  duration: "15m"
EOF

echo "[2/6] NetworkChaos: frontend 丢包 8%（根因叠加）"
kc_apply alicloud <<'EOF'
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: origin-frontend-loss
  namespace: seat-1
spec:
  action: loss
  mode: one
  selector:
    namespaces: [seat-1]
    labelSelectors:
      app: frontend
  loss:
    loss: "8"
    correlation: "40"
  duration: "15m"
EOF

echo "[3/6] NetworkChaos: productcatalogservice 380ms（噪声）"
kc_apply tencent <<'EOF'
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: catalog-stale-read-delay
  namespace: seat-1
spec:
  action: delay
  mode: one
  selector:
    namespaces: [seat-1]
    labelSelectors:
      app: productcatalogservice
  delay:
    latency: "380ms"
    correlation: "50"
    jitter: "120ms"
  duration: "15m"
EOF

echo "[4/6] NetworkChaos: recommendationservice 420ms（噪声）"
kc_apply alicloud <<'EOF'
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: recommend-cache-miss-delay
  namespace: seat-1
spec:
  action: delay
  mode: one
  selector:
    namespaces: [seat-1]
    labelSelectors:
      app: recommendationservice
  delay:
    latency: "420ms"
    correlation: "60"
    jitter: "150ms"
  duration: "15m"
EOF

echo "[5/6] NetworkChaos: checkoutservice -> mysql-orders 300ms（噪声）"
kc_apply alicloud <<'EOF'
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: checkout-db-connection-jitter
  namespace: seat-1
spec:
  action: delay
  mode: one
  selector:
    namespaces: [seat-1]
    labelSelectors:
      app: checkoutservice
  direction: to
  target:
    mode: all
    selector:
      namespaces: [seat-1]
      labelSelectors:
        app: mysql-orders
  delay:
    latency: "300ms"
    correlation: "50"
    jitter: "100ms"
  duration: "15m"
EOF

echo "[6/6] StressChaos: alicloud namespace Pod CPU 压力（噪声）"
kc_apply alicloud <<'EOF'
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: alicloud-node-cpu-pressure
  namespace: seat-1
spec:
  mode: all
  selector:
    namespaces: [seat-1]
  stressors:
    cpu:
      workers: 2
      load: 60
  duration: "15m"
EOF

echo "[inject] 完成。"
echo "[inject] 根因：origin-frontend-delay + origin-frontend-loss → 页面加载慢 + 资源加载失败"
echo "[inject] 噪声：catalog/recommend/checkout-db/cpu（分散注意力）"
