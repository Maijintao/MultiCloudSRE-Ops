#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib.sh"

echo "[recover] starting worker service"
target_run docker compose up -d worker
echo "[recover] current worker/redis/db status"
target_run docker compose ps worker redis db
