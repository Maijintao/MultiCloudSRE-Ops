#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib.sh"

echo "[recover] starting db service"
target_run docker compose up -d db
echo "[recover] restarting db clients"
target_run docker compose restart worker result
echo "[recover] current db/worker/result status"
target_run docker compose ps db worker result
