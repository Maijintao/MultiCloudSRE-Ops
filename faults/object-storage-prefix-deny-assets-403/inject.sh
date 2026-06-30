#!/usr/bin/env bash
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-injector.yaml}"
kc() { local ctx=$1; shift; kubectl --context="$ctx" -n seat-1 "$@"; }

BACKUP_CM="object-storage-prefix-deny-assets-403-backup"

backup_cluster() {
  local ctx=$1
  local tmp
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  for item in "configmap catalog-asset-routes" "configmap object-storage-policy" "deploy productcatalogservice" "deploy new-gatewayservice" "deploy asset-proxy" "service asset-proxy"; do
    set -- $item
    local kind=$1
    local name=$2
    local key="${ctx}-${kind}-${name}"
    if kc "$ctx" get "$kind" "$name" -o json >"$tmp/${key}.json" 2>/dev/null; then
      printf 'present' >"$tmp/${key}.present"
    else
      printf '{}' >"$tmp/${key}.json"
      printf 'missing' >"$tmp/${key}.present"
    fi
  done
  kc "$ctx" create configmap "$BACKUP_CM" --from-file="$tmp" --dry-run=client -o yaml | kc "$ctx" apply -f -
}

echo "[inject] object-storage-prefix-deny-assets-403: backup current resources"
backup_cluster tencent
backup_cluster alicloud

echo "[inject] make productcatalogservice publish 2026 asset prefix"
kc tencent create configmap catalog-asset-routes \
  --from-literal=asset_prefix='/assets/products/2026/' \
  --from-literal=image_base_url='https://assets.example.com/assets/products/2026/' \
  --from-literal=sample_product_json='{"id":"OLJCESPC7Z","name":"Vintage Camera","picture":"/assets/products/2026/OLJCESPC7Z.jpg"}' \
  --dry-run=client -o yaml | kc tencent apply -f -

kc tencent set env deploy/productcatalogservice \
  CATALOG_ASSET_ROUTES='catalog-asset-routes' \
  PRODUCT_IMAGE_PREFIX='/assets/products/2026/' \
  --overwrite
kc tencent annotate deploy/productcatalogservice \
  sre-test/fault='object-storage-prefix-deny-assets-403' \
  --overwrite

kc tencent set env deploy/new-gatewayservice \
  ASSET_PROXY_BASE='http://asset-proxy.seat-1.svc.cluster.local' \
  --overwrite
kc tencent annotate deploy/new-gatewayservice \
  sre-test/fault='object-storage-prefix-deny-assets-403' \
  --overwrite

echo "[inject] deny the active object storage prefix on tencent asset-proxy"
kc tencent create configmap object-storage-policy \
  --from-literal=allowPrefixes='oss://shop-assets/products/2025/*,oss://shop-assets/public/*' \
  --from-literal=denyPrefixes='oss://shop-assets/products/2026/*' \
  --from-literal=diagnostic_headers='X-Asset-Policy-Decision: deny-prefix; X-Asset-Prefix: oss://shop-assets/products/2026/' \
  --from-literal=default.conf='server {
    listen 8080;
    location /assets/products/2026/ {
      add_header X-Asset-Policy-Decision "deny-prefix" always;
      add_header X-Asset-Prefix "oss://shop-assets/products/2026/" always;
      return 403 "object storage prefix denied\n";
    }
    location / {
      add_header X-Asset-Policy-Decision "allow" always;
      return 200 "asset proxy ok\n";
    }
  }' \
  --dry-run=client -o yaml | kc tencent apply -f -

kc tencent apply -f - <<'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: asset-proxy
  namespace: seat-1
  labels:
    app: asset-proxy
spec:
  replicas: 1
  selector:
    matchLabels:
      app: asset-proxy
  template:
    metadata:
      labels:
        app: asset-proxy
      annotations:
        sre-test/fault: object-storage-prefix-deny-assets-403
        sre-test/evidence: asset-api-200-object-prefix-403
    spec:
      containers:
      - name: server
        image: nginx
        ports:
        - containerPort: 8080
        env:
        - name: OBJECT_STORAGE_POLICY_CONFIG
          value: object-storage-policy
        - name: ASSET_BUCKET
          value: shop-assets
        - name: BLOCKED_PREFIX
          value: oss://shop-assets/products/2026/
        volumeMounts:
        - name: policy
          mountPath: /etc/nginx/conf.d/default.conf
          subPath: default.conf
      volumes:
      - name: policy
        configMap:
          name: object-storage-policy
          items:
          - key: default.conf
            path: default.conf
YAML


kc tencent apply -f - <<'YAML'
apiVersion: v1
kind: Service
metadata:
  name: asset-proxy
  namespace: seat-1
  labels:
    app: asset-proxy
spec:
  selector:
    app: asset-proxy
  ports:
  - name: http
    port: 80
    targetPort: 8080
YAML

echo "[inject] complete: catalog emits 2026 asset URLs, asset-proxy policy denies that prefix."
