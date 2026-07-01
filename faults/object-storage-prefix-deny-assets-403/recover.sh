#!/usr/bin/env bash
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-injector.yaml}"
kc() { local ctx=$1; shift; kubectl --context="$ctx" -n seat-1 "$@"; }

BACKUP_CM="object-storage-prefix-deny-assets-403-backup"
CASE_ID="object-storage-prefix-deny-assets-403"

backup_exists() {
  local ctx=$1
  kc "$ctx" get configmap "$BACKUP_CM" >/dev/null 2>&1
}

resource_exists() {
  local ctx=$1 kind=$2 name=$3
  kc "$ctx" get "$kind" "$name" >/dev/null 2>&1
}

object_annotation() {
  local ctx=$1 kind=$2 name=$3 annotation=$4
  kc "$ctx" get "$kind" "$name" -o "go-template={{ index .metadata.annotations \"${annotation}\" }}" 2>/dev/null || true
}

template_annotation() {
  local ctx=$1 kind=$2 name=$3 annotation=$4
  kc "$ctx" get "$kind" "$name" -o "go-template={{ index .spec.template.metadata.annotations \"${annotation}\" }}" 2>/dev/null || true
}

config_value() {
  local ctx=$1 name=$2 key=$3
  kc "$ctx" get configmap "$name" -o "go-template={{ index .data \"${key}\" }}" 2>/dev/null || true
}

restore_resource() {
  local ctx=$1 kind=$2 name=$3
  local key="${ctx}-${kind}-${name}" tmp cm_file json_file present_file
  if ! backup_exists "$ctx"; then
    echo "[recover] backup ConfigMap/${BACKUP_CM} not found on ${ctx}; skip direct restore for ${kind}/${name}"
    return 0
  fi

  tmp="$(mktemp -d)"
  cm_file="$tmp/backup-cm.json"
  json_file="$tmp/resource.json"
  present_file="$tmp/present"
  kc "$ctx" get configmap "$BACKUP_CM" -o json >"$cm_file"
  python3 - "$cm_file" "$key" "$json_file" "$present_file" <<'PY'
import json, sys
cm_file, key, json_file, present_file = sys.argv[1:5]
cm = json.load(open(cm_file))
data = cm.get("data", {})
open(json_file, "w").write(data.get(key + ".json", "{}"))
open(present_file, "w").write(data.get(key + ".present", "missing"))
PY
  if [ "$(cat "$present_file")" = "present" ]; then
    python3 - "$json_file" <<'PY' | kc "$ctx" apply -f -
import json, sys
obj = json.load(open(sys.argv[1]))
meta = obj.setdefault("metadata", {})
for field in ["uid", "resourceVersion", "generation", "creationTimestamp", "managedFields"]:
    meta.pop(field, None)
obj.pop("status", None)
print(json.dumps(obj))
PY
  else
    kc "$ctx" delete "$kind" "$name" --ignore-not-found=true
  fi
  rm -rf "$tmp"
}

cleanup_injected_leftovers() {
  local ctx=$1
  local value deployment_fault asset_proxy_fault

  value="$(config_value "$ctx" catalog-asset-routes asset_prefix)"
  if [ "$value" = "/assets/products/2026/" ]; then
    kc "$ctx" delete configmap catalog-asset-routes --ignore-not-found=true
  fi

  value="$(config_value "$ctx" object-storage-policy denyPrefixes)"
  if [[ "$value" == *"oss://shop-assets/products/2026/"* ]]; then
    kc "$ctx" delete configmap object-storage-policy --ignore-not-found=true
  fi

  deployment_fault="$(object_annotation "$ctx" deploy productcatalogservice sre-test/fault)"
  if [ "$deployment_fault" = "$CASE_ID" ]; then
    kc "$ctx" set env deploy/productcatalogservice CATALOG_ASSET_ROUTES- PRODUCT_IMAGE_PREFIX- 2>/dev/null || true
    kc "$ctx" annotate deploy/productcatalogservice sre-test/fault- 2>/dev/null || true
  fi

  deployment_fault="$(object_annotation "$ctx" deploy new-gatewayservice sre-test/fault)"
  if [ "$deployment_fault" = "$CASE_ID" ]; then
    kc "$ctx" set env deploy/new-gatewayservice ASSET_PROXY_BASE- 2>/dev/null || true
    kc "$ctx" annotate deploy/new-gatewayservice sre-test/fault- 2>/dev/null || true
  fi

  asset_proxy_fault="$(template_annotation "$ctx" deploy asset-proxy sre-test/fault)"
  if [ "$asset_proxy_fault" = "$CASE_ID" ]; then
    kc "$ctx" delete deploy asset-proxy --ignore-not-found=true
    kc "$ctx" delete service asset-proxy --ignore-not-found=true
  fi
}

wait_rollout_if_exists() {
  local ctx=$1 name=$2
  if resource_exists "$ctx" deploy "$name"; then
    kc "$ctx" rollout status "deploy/${name}" --timeout=120s
  else
    echo "[recover] deployment/${name} is absent after restore; skip rollout wait"
  fi
}

echo "[recover] object-storage-prefix-deny-assets-403: restore backed up resources"
restore_resource tencent configmap catalog-asset-routes
restore_resource tencent configmap object-storage-policy
restore_resource tencent deploy productcatalogservice
restore_resource tencent deploy new-gatewayservice
restore_resource tencent deploy asset-proxy
restore_resource tencent service asset-proxy

echo "[recover] clean known injected leftovers"
cleanup_injected_leftovers tencent

echo "[recover] waiting for existing deployments..."
wait_rollout_if_exists tencent productcatalogservice
wait_rollout_if_exists tencent new-gatewayservice
wait_rollout_if_exists tencent asset-proxy

kc tencent delete configmap "$BACKUP_CM" --ignore-not-found=true
kc alicloud delete configmap "$BACKUP_CM" --ignore-not-found=true

echo "[recover] complete."
