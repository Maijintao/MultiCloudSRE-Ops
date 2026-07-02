#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-injector.yaml}"
kc() { local ctx=$1; shift; kubectl --context="$ctx" -n seat-1 "$@"; }
kc_apply() { local ctx=$1; shift; kc "$ctx" apply -f - "$@"; }
PID_FILE=/tmp/dns-chaos-payment.pid
LOG_FILE=/tmp/dns-chaos-payment.log

echo "[inject] dns-chaos: DNS 解析故障注入"

# 故障 1: 腾讯云 productcatalogservice DNS 解析失败（并行）
echo "[1/3] DNSChaos: productcatalogservice DNS error (腾讯云)"
kc_apply tencent <<'EOF' &
apiVersion: chaos-mesh.org/v1alpha1
kind: DNSChaos
metadata:
  name: dns-chaos-productcatalog
  namespace: seat-1
spec:
  action: error
  mode: all
  selector:
    namespaces: [seat-1]
  patterns:
    - "productcatalogservice.*"
  duration: "15m"
EOF

# 故障 2: AWS paymentservice DNS 解析随机 IP (延迟 30 秒)
echo "[2/3] DNSChaos: paymentservice DNS random (AWS, T+30s)"
# 清理历史后台任务标记，避免旧任务干扰
rm -f "$PID_FILE" "$LOG_FILE"
# Write delayed-injection YAML to temp file
DELAYED_YAML=$(mktemp /tmp/dns-chaos-delayed-XXXXXX.yaml)
cat > "$DELAYED_YAML" <<'EOF'
apiVersion: chaos-mesh.org/v1alpha1
kind: DNSChaos
metadata:
  name: dns-chaos-payment
  namespace: seat-1
spec:
  action: random
  mode: all
  selector:
    namespaces: [seat-1]
  patterns:
    - "paymentservice.*"
  duration: "15m"
EOF
nohup bash -c "sleep 30; kubectl --kubeconfig=\"\${KUBECONFIG:-\$HOME/.kube/config-injector.yaml}\" --context=aws -n seat-1 apply -f $DELAYED_YAML; rm -f $DELAYED_YAML" > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

# 故障 3: 阿里云 recommendationservice DNS 故障 (10 秒后自愈，并行)
echo "[3/3] DNSChaos: recommendationservice DNS random (阿里云, 10s 自愈)"
kc_apply alicloud <<'EOF' &
apiVersion: chaos-mesh.org/v1alpha1
kind: DNSChaos
metadata:
  name: dns-chaos-recommendation
  namespace: seat-1
spec:
  action: random
  mode: all
  selector:
    namespaces: [seat-1]
  patterns:
    - "recommendationservice.*"
  duration: "10s"
EOF

wait
echo "[inject] 所有 DNS 故障已注入，paymentservice 将在 T+30s 生效"
