#!/bin/bash
# 05 - 上传并导入镜像 tar 到 containerd

if [[ "${SKIP_IMAGE_IMPORT:-false}" == "true" ]]; then
  log "SKIP_IMAGE_IMPORT=true, 跳过镜像导入"
  return 0 2>/dev/null || exit 0
fi

log "导入镜像到三台服务器..."

import_images_for() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5" cloud_dir="$6"

  log "  导入镜像到 $label ($ip)..."

  # 创建远程目录
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "mkdir -p /tmp/sre-images"

  # 上传通用镜像
  if ls "$SCRIPT_DIR/../images/common/"*.tar &>/dev/null; then
    for tar in "$SCRIPT_DIR/../images/common/"*.tar; do
      log "    上传 $(basename $tar) ..."
      scp_upload "$tar" "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-images/"
    done
  fi

  # 上传云特定镜像
  if ls "$SCRIPT_DIR/../images/${cloud_dir}/"*.tar &>/dev/null; then
    for tar in "$SCRIPT_DIR/../images/${cloud_dir}/"*.tar; do
      log "    上传 $(basename $tar) ..."
      scp_upload "$tar" "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-images/"
    done
  fi

  # 导入所有镜像
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    for tar in /tmp/sre-images/*.tar; do
      echo \"导入: \$(basename \$tar)\"
      sudo k3s ctr images import \$tar 2>/dev/null || k3s ctr images import \$tar
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
