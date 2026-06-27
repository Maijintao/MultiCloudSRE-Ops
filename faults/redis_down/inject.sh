#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib.sh"

echo "[inject] stopping redis service"
target_run docker compose stop redis
echo "[inject] current redis/vote/worker status"
target_run docker compose ps redis vote worker
