#!/bin/bash
# 构建 hermes-agent Docker 镜像并导出为 tar.gz，用于 release 分发。
# 用法: bash scripts/package-hermes-image.sh [output_dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${1:-$PROJECT_DIR/dist}"
IMAGE_NAME="${OJ_HERMES_DOCKER_IMAGE:-hermes-agent:latest}"
DOCKERFILE="$PROJECT_DIR/docker/hermes-runtime.Dockerfile"

mkdir -p "$OUTPUT_DIR"

echo "[package] Building Hermes runtime image..."
docker build \
  -t "$IMAGE_NAME" \
  -f "$DOCKERFILE" \
  "$PROJECT_DIR"

echo "[package] Exporting image to tar.gz..."
docker save "$IMAGE_NAME" | gzip > "$OUTPUT_DIR/hermes-agent-image.tar.gz"

size=$(du -h "$OUTPUT_DIR/hermes-agent-image.tar.gz" | cut -f1)
echo "[package] Done: $OUTPUT_DIR/hermes-agent-image.tar.gz ($size)"
echo "[package] Upload this file to the GitHub Release alongside the deploy bundle."
