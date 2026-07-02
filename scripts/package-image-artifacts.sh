#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGES_DIR="${IMAGES_DIR:-$SCRIPT_DIR/images}"
OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR/dist/image-artifacts}"

if [[ ! -d "$IMAGES_DIR" ]]; then
  echo "镜像目录不存在: $IMAGES_DIR" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

package_dir() {
  local name="$1"
  local src="$IMAGES_DIR/$name"
  local output="$OUTPUT_DIR/${name}-image-tars.tar.gz"

  if [[ ! -d "$src" ]] || ! find "$src" -maxdepth 1 -type f -name '*.tar' ! -name '._*.tar' | grep -q .; then
    echo "跳过 $name: 未找到 $src/*.tar"
    return 0
  fi

  echo "打包 $name -> $output"
  COPYFILE_DISABLE=1 tar -czf "$output" -C "$IMAGES_DIR" "$name"
}

package_dir common
package_dir aliyun
package_dir tencent
package_dir aws

echo "完成: $OUTPUT_DIR"
ls -lh "$OUTPUT_DIR"
