#!/usr/bin/env bash
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-injector.yaml}"
kc() { local ctx=$1; shift; kubectl --context="$ctx" -n seat-1 "$@"; }

echo "[recover] challenge-33: remove payment clock skew"

kc aws delete timechaos payment-clock-skew --ignore-not-found

echo "[recover] complete. Verify paymentservice date."
