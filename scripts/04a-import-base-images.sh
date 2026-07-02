#!/bin/bash
# 04a - 导入 k3s/Chaos Mesh 基础镜像（必须在安装 Chaos Mesh 前执行）
# 本地下载后 SCP 到服务器，避免服务器直连外网

if [[ "${SKIP_BASE_IMAGE_IMPORT:-false}" == "true" ]]; then
  log "SKIP_BASE_IMAGE_IMPORT=true, 跳过基础镜像导入"
  return 0 2>/dev/null || exit 0
fi

BASE_IMAGE_BUNDLE_NAME="${BASE_IMAGE_BUNDLE_NAME:-k3s-chaos-base-images.tar}"
BASE_IMAGE_ARTIFACT_URL="${BASE_IMAGE_ARTIFACT_URL:-}"
BASE_IMAGE_TAR_PATH="${BASE_IMAGE_TAR_PATH:-}"

if [[ -z "$BASE_IMAGE_ARTIFACT_URL" && -n "${IMAGE_ARTIFACT_BASE_URL:-}" ]]; then
  BASE_IMAGE_ARTIFACT_URL="${IMAGE_ARTIFACT_BASE_URL%/}/${BASE_IMAGE_BUNDLE_NAME}"
fi

if [[ -z "$BASE_IMAGE_ARTIFACT_URL" && -z "$BASE_IMAGE_TAR_PATH" ]]; then
  warn "未配置 BASE_IMAGE_ARTIFACT_URL/BASE_IMAGE_TAR_PATH，跳过基础镜像预导入；公网受限环境可能无法安装 Chaos Mesh"
  return 0 2>/dev/null || exit 0
fi

IMAGE_ARTIFACT_CACHE_DIR="${IMAGE_ARTIFACT_CACHE_DIR:-$SCRIPT_DIR/dist/image-artifacts-cache}"

# 确保本地有基础镜像 tar
ensure_local_base_image() {
  if [[ -n "$BASE_IMAGE_TAR_PATH" ]]; then
    if [[ ! -f "$BASE_IMAGE_TAR_PATH" ]]; then
      err "BASE_IMAGE_TAR_PATH 不存在: $BASE_IMAGE_TAR_PATH"
      exit 1
    fi
    return 0
  fi

  local cached="$IMAGE_ARTIFACT_CACHE_DIR/$BASE_IMAGE_BUNDLE_NAME"
  if [[ -s "$cached" ]]; then
    log "  本地基础镜像已缓存: $cached"
    BASE_IMAGE_TAR_PATH="$cached"
    return 0
  fi

  log "  本地下载基础镜像 ($(basename "$BASE_IMAGE_ARTIFACT_URL"))..."
  mkdir -p "$IMAGE_ARTIFACT_CACHE_DIR"
  curl --http1.1 -fL --retry 5 --retry-delay 5 --connect-timeout 20 --max-time 1800 \
    -o "$cached" "$BASE_IMAGE_ARTIFACT_URL"
  BASE_IMAGE_TAR_PATH="$cached"
  log "  基础镜像下载完成: $(du -h "$cached" | cut -f1)"
}

ensure_local_base_image

log "导入 k3s/Chaos Mesh 基础镜像..."
log "  本地文件: $BASE_IMAGE_TAR_PATH"

import_base_images_for_host() {
  local role="$1"
  local ip user pass_var key_var label sudo_prefix remote_tar

  ip="$(role_ip "$role")"
  user="$(role_user "$role")"
  pass_var="$(role_pass_var "$role")"
  key_var="$(role_key_var "$role")"
  label="$(role_label "$role")"
  sudo_prefix="$(remote_priv_prefix "$user")"
  remote_tar="/tmp/sre-base-images/${BASE_IMAGE_BUNDLE_NAME}"

  log "  导入基础镜像到 $label ($ip)..."

  local chaos_ok=0 pause_ok=0
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "${sudo_prefix}k3s kubectl get ns chaos-mesh >/dev/null 2>&1" && chaos_ok=1
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "${sudo_prefix}k3s ctr images ls -q 2>/dev/null | grep -q 'rancher/mirrored-pause'" && pause_ok=1
  if [[ $chaos_ok -eq 1 && $pause_ok -eq 1 ]]; then
    log "  $label 已安装 Chaos Mesh 且 pause 镜像存在，跳过基础镜像重复导入"
    return 0
  fi

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "rm -rf /tmp/sre-base-images && mkdir -p /tmp/sre-base-images"

  scp_upload "$BASE_IMAGE_TAR_PATH" "$ip" "$user" "$pass_var" "$key_var" "$remote_tar"

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    set -e
    ctr_cmd='k3s ctr'
    if [[ \$(id -u) -ne 0 ]]; then
      ctr_cmd='sudo -n k3s ctr'
    fi
    test -s '$remote_tar'
    \$ctr_cmd images import '$remote_tar'
    rm -rf /tmp/sre-base-images
  "

  log "  $label 基础镜像导入完成"
}

fail=0
pids=()
labels=()
for role in $(unique_role_hosts); do
  import_base_images_for_host "$role" &
  pids+=("$!")
  labels+=("$(role_label "$role")")
done

for i in "${!pids[@]}"; do
  wait "${pids[$i]}" || { err "${labels[$i]} 基础镜像导入失败"; fail=1; }
done

[[ $fail -eq 1 ]] && exit 1

log "基础镜像导入完成"
