#!/bin/bash
set -euo pipefail

cloud="${1:?cloud is required}"
public_ip="${2:?public ip is required}"

if [[ "$(id -u)" -eq 0 ]]; then
  KUBECTL="k3s kubectl"
else
  KUBECTL="sudo -n k3s kubectl"
fi

out_dir="/tmp/sre-access"
mkdir -p "$out_dir"

for manifest in \
  /tmp/sre-readonly.yaml \
  /tmp/sre-injector.yaml \
  /tmp/sre-chaos-dashboard.yaml
do
  if [[ -f "$manifest" ]]; then $KUBECTL apply -f "$manifest" >/dev/null; fi
done

get_token() {
  local ns="$1"
  local sa="$2"
  local token

  token="$($KUBECTL create token "$sa" -n "$ns" --duration=87600h 2>/dev/null || true)"
  if [[ -n "$token" ]]; then
    printf "%s\n" "$token"
    return 0
  fi

  local secret="${sa}-token"
  cat <<EOF | $KUBECTL apply -f - >/dev/null
apiVersion: v1
kind: Secret
metadata:
  name: ${secret}
  namespace: ${ns}
  annotations:
    kubernetes.io/service-account.name: ${sa}
type: kubernetes.io/service-account-token
EOF

  for _ in $(seq 1 30); do
    token="$($KUBECTL get secret "$secret" -n "$ns" -o jsonpath='{.data.token}' 2>/dev/null || true)"
    if [[ -n "$token" ]]; then
      printf "%s\n" "$token" | base64 -d
      printf "\n"
      return 0
    fi
    sleep 1
  done

  echo "failed to create token for ${ns}/${sa}" >&2
  return 1
}

write_kubeconfig() {
  local name="$1"
  local token="$2"
  local file="$3"

  cat > "$file" <<EOF
apiVersion: v1
kind: Config
clusters:
- name: ${name}
  cluster:
    server: https://${public_ip}:6443
    insecure-skip-tls-verify: true
users:
- name: ${name}
  user:
    token: ${token}
contexts:
- name: ${name}
  context:
    cluster: ${name}
    user: ${name}
    namespace: seat-1
current-context: ${name}
EOF
}

readonly_token="$(get_token seat-1 sre-readonly)"
injector_token="$(get_token seat-1 sre-injector)"
dashboard_token="$(get_token chaos-mesh sre-chaos-dashboard)"

write_kubeconfig "sre-${cloud}-readonly" "$readonly_token" "$out_dir/${cloud}-readonly.kubeconfig"
write_kubeconfig "sre-${cloud}-injector" "$injector_token" "$out_dir/${cloud}-injector.kubeconfig"
printf "%s\n" "$dashboard_token" > "$out_dir/${cloud}-chaos-dashboard.token"
chmod 600 "$out_dir"/*

echo "generated access files in $out_dir"
