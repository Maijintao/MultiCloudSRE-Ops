#!/bin/bash
# 05 - 上传并导入镜像 tar 到 containerd

if [[ "${SKIP_IMAGE_IMPORT:-false}" == "true" ]]; then
  log "SKIP_IMAGE_IMPORT=true, 跳过镜像导入"
  return 0 2>/dev/null || exit 0
fi

log "导入镜像到三台服务器..."

IMAGES_DIR="${IMAGES_DIR:-$SCRIPT_DIR/images}"

if [[ ! -d "$IMAGES_DIR" ]]; then
  err "镜像目录不存在: $IMAGES_DIR"
  exit 1
fi

log "镜像目录: $IMAGES_DIR"

import_images_for() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5" cloud_dir="$6"
  local uploaded=0

  log "  导入镜像到 $label ($ip)..."

  # 创建远程目录
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "mkdir -p /tmp/sre-images"

  # 上传通用镜像
  for tar in "$IMAGES_DIR/common/"*.tar; do
    [[ -f "$tar" ]] || continue
    log "    上传 $(basename "$tar") ..."
    scp_upload "$tar" "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-images/"
    uploaded=1
  done

  # 上传云特定镜像
  for tar in "$IMAGES_DIR/${cloud_dir}/"*.tar; do
    [[ -f "$tar" ]] || continue
    log "    上传 $(basename "$tar") ..."
    scp_upload "$tar" "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-images/"
    uploaded=1
  done

  if [[ $uploaded -eq 0 ]]; then
    err "$label 未找到可导入镜像: $IMAGES_DIR/common/*.tar 或 $IMAGES_DIR/${cloud_dir}/*.tar"
    return 1
  fi

  # 导入所有镜像
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    set -e
    ctr_cmd='k3s ctr'
    if [[ \$(id -u) -ne 0 ]]; then
      ctr_cmd='sudo -n k3s ctr'
    fi

    found=0
    for tar in /tmp/sre-images/*.tar; do
      [[ -f \"\$tar\" ]] || continue
      found=1
      echo \"导入: \$(basename \$tar)\"
      \$ctr_cmd images import \"\$tar\"
    done
    [[ \$found -eq 1 ]] || { echo '未找到 /tmp/sre-images/*.tar' >&2; exit 1; }

    # k8s 会把短镜像名规范化为 docker.io/library/*；离线 tar 里若只有短名，
    # imagePullPolicy=Never 时需要补齐等价 tag。
    \$ctr_cmd images ls -q | while read -r tag; do
      [[ -n "\$tag" ]] || continue
      [[ "\$tag" == */* ]] && continue
      [[ "\$tag" == *:* ]] || continue
      \$ctr_cmd images tag --force "\$tag" "docker.io/library/\$tag" >/dev/null 2>&1 || true
    done

    rm -rf /tmp/sre-images
  "

  log "  $label 镜像导入完成"
}

import_images_for "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" "阿里云" "aliyun" &
pid1=$!
import_images_for "$TENCENT_IP" "$TENCENT_USER" "TENCENT_PASS" "TENCENT_KEY" "腾讯云" "tencent" &
pid2=$!
import_images_for "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" "AWS" "aws" &
pid3=$!

fail=0
wait $pid1 || { err "阿里云镜像导入失败"; fail=1; }
wait $pid2 || { err "腾讯云镜像导入失败"; fail=1; }
wait $pid3 || { err "AWS 镜像导入失败"; fail=1; }

[[ $fail -eq 1 ]] && exit 1

log "镜像导入完成（三台）"
