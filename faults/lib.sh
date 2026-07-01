#!/usr/bin/env bash
set -euo pipefail

target_run() {
  local app_dir="${VOTING_APP_DIR:-/opt/example-voting-app}"
  if [[ -n "${FAULT_TARGET_HOST:-}" ]]; then
    local user="${FAULT_TARGET_USER:-root}"
    local port="${FAULT_TARGET_PORT:-22}"
    local identity="${FAULT_TARGET_IDENTITY_FILE:-}"
    local remote_cmd="cd $(printf '%q' "$app_dir") &&"
    local arg
    for arg in "$@"; do
      remote_cmd+=" $(printf '%q' "$arg")"
    done

    local ssh_cmd=(
      ssh
      -o StrictHostKeyChecking=accept-new
      -o ServerAliveInterval=30
      -p "$port"
    )
    if [[ -n "$identity" ]]; then
      ssh_cmd+=(-i "$identity")
    fi
    ssh_cmd+=("${user}@${FAULT_TARGET_HOST}" "$remote_cmd")
    if [[ -n "${FAULT_TARGET_PASSWORD:-}" ]] && command -v sshpass >/dev/null 2>&1; then
      sshpass -p "$FAULT_TARGET_PASSWORD" "${ssh_cmd[@]}"
    else
      "${ssh_cmd[@]}"
    fi
    return
  fi

  (cd "$app_dir" && "$@")
}
