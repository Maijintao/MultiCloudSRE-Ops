#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib.sh"

echo "[inject] stopping db service"
target_run docker compose stop db
echo "[inject] current db/worker/result status"
target_run docker compose ps db worker result
