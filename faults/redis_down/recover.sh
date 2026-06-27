#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib.sh"

echo "[recover] starting redis service"
target_run docker compose up -d redis
echo "[recover] restarting redis clients"
target_run docker compose restart vote worker
echo "[recover] current redis/vote/worker status"
target_run docker compose ps redis vote worker
