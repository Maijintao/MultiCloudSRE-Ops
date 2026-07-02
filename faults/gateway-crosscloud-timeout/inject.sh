#!/usr/bin/env bash
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-injector.yaml}"
kc() { local ctx=$1; shift; kubectl --context="$ctx" -n seat-1 "$@"; }
kc_apply() { local ctx=$1; shift; kc "$ctx" apply -f - "$@"; }

AWS_ORDER_HOST="${AWS_ORDER_HOST:-${SERVER3_IP:-203.0.113.30}}"

echo "[inject] challenge-31: 腾讯云 gateway 跨云调用级联超时（三层叠加 + 干扰）"
echo "[inject] external target: ${AWS_ORDER_HOST} (AWS new-orderservice NodePort host)"

# 并行：chaos 创建 + env 设置（不同资源互不阻塞）
kc_apply tencent <<EOF &
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: gw-to-aws-order-delay
  namespace: seat-1
spec:
  action: delay
  mode: one
  selector:
    namespaces: [seat-1]
    labelSelectors:
      app: new-gatewayservice
  direction: to
  externalTargets:
    - "${AWS_ORDER_HOST}"
  delay:
    latency: "400ms"
    correlation: "70"
    jitter: "150ms"
EOF

kc_apply tencent <<EOF &
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: gw-to-aws-order-loss
  namespace: seat-1
spec:
  action: loss
  mode: one
  selector:
    namespaces: [seat-1]
    labelSelectors:
      app: new-gatewayservice
  direction: to
  externalTargets:
    - "${AWS_ORDER_HOST}"
  loss:
    loss: "12"
    correlation: "50"
EOF

kc_apply tencent <<'EOF' &
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: tencent-global-cpu-stress
  namespace: seat-1
spec:
  mode: all
  selector:
    namespaces: [seat-1]
  stressors:
    cpu:
      workers: 2
      load: 50
EOF

# env 操作（触发滚动更新，耗时最长）
kc tencent set env deploy/new-gatewayservice UPSTREAM_TIMEOUT=500ms MAX_RETRIES=0 --overwrite &

wait

echo "[inject] 完成。"
echo "[inject] 三层叠加：到 AWS 外部目标的延迟 400±150ms + 丢包 12% + 超时 500ms"
echo "[inject] 干扰项：全命名空间 CPU 压力"
