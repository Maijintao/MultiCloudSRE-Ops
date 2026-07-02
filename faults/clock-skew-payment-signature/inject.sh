#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-injector.yaml}"
kc() { local ctx=$1; shift; kubectl --context="$ctx" -n seat-1 "$@"; }
kc_apply() { local ctx=$1; shift; kc "$ctx" apply -f - "$@"; }

echo "[inject] challenge-33: AWS paymentservice clock skew"

kc_apply aws <<'EOF'
apiVersion: chaos-mesh.org/v1alpha1
kind: TimeChaos
metadata:
  name: payment-clock-skew
  namespace: seat-1
spec:
  mode: one
  selector:
    namespaces:
      - seat-1
    labelSelectors:
      app: paymentservice
  timeOffset: "-10m"
  duration: "15m"
EOF

echo "[inject] complete. paymentservice 时间偏移 -10m，会导致签名校验失败。"
