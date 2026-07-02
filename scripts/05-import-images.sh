#!/bin/bash
# 05 - 上传并导入镜像 tar 到 containerd

if [[ "${SKIP_IMAGE_IMPORT:-false}" == "true" ]]; then
  log "SKIP_IMAGE_IMPORT=true, 跳过镜像导入"
  return 0 2>/dev/null || exit 0
fi

log "导入镜像到服务器..."

IMAGES_DIR="${IMAGES_DIR:-$SCRIPT_DIR/images}"
IMAGE_ARTIFACT_BASE_URL="${IMAGE_ARTIFACT_BASE_URL:-}"
IMAGE_IMPORT_MODE="${IMAGE_IMPORT_MODE:-local}"
IMAGE_ARTIFACT_CACHE_DIR="${IMAGE_ARTIFACT_CACHE_DIR:-$SCRIPT_DIR/dist/image-artifacts-cache}"

case "$IMAGE_IMPORT_MODE" in
  local|remote) ;;
  auto) IMAGE_IMPORT_MODE="local" ;;
  *)
    err "IMAGE_IMPORT_MODE 只能是 local、remote 或 auto，当前: $IMAGE_IMPORT_MODE"
    exit 1
    ;;
esac

if [[ -n "$IMAGE_ARTIFACT_BASE_URL" ]]; then
  IMAGE_ARTIFACT_BASE_URL="${IMAGE_ARTIFACT_BASE_URL%/}"
fi
log "镜像导入模式: $IMAGE_IMPORT_MODE"
if [[ -n "$IMAGE_ARTIFACT_BASE_URL" ]]; then log "镜像制品 URL: $IMAGE_ARTIFACT_BASE_URL"; fi
log "本地镜像目录: $IMAGES_DIR"

local_image_dir_has_tar() {
  local dir="$1"
  [[ -d "$dir" ]] || return 1
  find "$dir" -maxdepth 1 -type f -name '*.tar' ! -name '._*.tar' | grep -q .
}

required_local_bundles() {
  local seen="
common
"
  local role cloud
  echo "common"
  for role in server1 server2 server3; do
    cloud="$(role_cloud_dir "$role")"
    case "$seen" in
      *"
$cloud
"*) ;;
      *)
        seen="${seen}${cloud}
"
        echo "$cloud"
        ;;
    esac
  done
}

ensure_local_images() {
  local missing=0 name bundle bundle_path url

  for name in $(required_local_bundles); do
    if ! local_image_dir_has_tar "$IMAGES_DIR/$name"; then
      missing=1
      break
    fi
  done

  if [[ $missing -eq 0 ]]; then
    log "本地镜像 tar 已就绪"
    return 0
  fi

  if [[ -z "$IMAGE_ARTIFACT_BASE_URL" ]]; then
    err "本地镜像不完整，且未配置 IMAGE_ARTIFACT_BASE_URL，无法自动下载镜像包"
    exit 1
  fi

  mkdir -p "$IMAGES_DIR" "$IMAGE_ARTIFACT_CACHE_DIR"
  log "本地镜像不完整，开始从 Release/制品地址下载并解压..."

  for name in $(required_local_bundles); do
    if local_image_dir_has_tar "$IMAGES_DIR/$name"; then
      log "  $name 镜像已存在，跳过下载"
      continue
    fi

    bundle="${name}-image-tars.tar.gz"
    bundle_path="$IMAGE_ARTIFACT_CACHE_DIR/$bundle"
    url="$IMAGE_ARTIFACT_BASE_URL/$bundle"

    log "  下载 $bundle"
    curl --http1.1 -fL --retry 5 --retry-delay 5 --connect-timeout 20 --max-time 1800 \
      -o "$bundle_path" "$url"

    log "  解压 $bundle -> $IMAGES_DIR"
    tar -xzf "$bundle_path" -C "$IMAGES_DIR"
    find "$IMAGES_DIR" -name '._*' -delete
  done
}

if [[ "$IMAGE_IMPORT_MODE" == "local" ]]; then
  ensure_local_images
elif [[ -z "$IMAGE_ARTIFACT_BASE_URL" ]]; then
  err "IMAGE_IMPORT_MODE=remote 时必须配置 IMAGE_ARTIFACT_BASE_URL"
  exit 1
fi

upload_tar_dir() {
  local dir="$1" ip="$2" user="$3" pass_var="$4" key_var="$5"
  local uploaded_var="$6"
  local tar

  for tar in "$dir/"*.tar; do
    [[ -f "$tar" ]] || continue
    if [[ "$(basename "$tar")" == ._* ]]; then continue; fi
    log "    上传 $(basename "$tar") ..."
    scp_upload "$tar" "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-images/"
    printf -v "$uploaded_var" "1"
  done
}

import_images_for_host() {
  local role="$1"
  local ip user pass_var key_var label roles role_cloud uploaded=0 bundles bundle_list use_aria2

  ip="$(role_ip "$role")"
  user="$(role_user "$role")"
  pass_var="$(role_pass_var "$role")"
  key_var="$(role_key_var "$role")"
  label="$(role_label "$role")"
  roles="$(host_roles_for_ip "$ip")"
  sudo_prefix="$(remote_priv_prefix "$user")"
  use_aria2=0
  if [[ "$IMAGE_ARTIFACT_BASE_URL" == https://github.com/* ]]; then use_aria2=1; fi

  log "  导入镜像到 $label ($ip)，承载角色: $roles"

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "rm -rf /tmp/sre-images && mkdir -p /tmp/sre-images"

  if [[ "$IMAGE_IMPORT_MODE" == "remote" ]]; then
    bundles="common-image-tars.tar.gz"
    for role in $roles; do
      role_cloud="$(role_cloud_dir "$role")"
      bundles="$bundles ${role_cloud}-image-tars.tar.gz"
    done
    bundle_list="$bundles"

    ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
      set -e
      cd /tmp/sre-images
      if ! command -v aria2c >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
        ${sudo_prefix}apt-get update
        ${sudo_prefix}apt-get install -y aria2 || true
      fi
      for bundle in $bundle_list; do
        echo \"下载镜像包: \$bundle\"
        if [[ '$use_aria2' == '1' ]] && command -v aria2c >/dev/null 2>&1; then
          aria2c -x 8 -s 8 -k 1M --retry-wait=5 --max-tries=5 \
            --connect-timeout=20 --timeout=120 \
            -d /tmp -o \"\$bundle\" \"$IMAGE_ARTIFACT_BASE_URL/\$bundle\"
        else
          curl --http1.1 -fL --retry 5 --retry-delay 5 --connect-timeout 20 --max-time 1800 \
            -o \"/tmp/\$bundle\" \"$IMAGE_ARTIFACT_BASE_URL/\$bundle\"
        fi
        tar -xzf \"/tmp/\$bundle\" -C /tmp/sre-images
        find /tmp/sre-images -type f -name '._*.tar' -delete
        rm -f \"/tmp/\$bundle\"
      done
    "
  else
    upload_tar_dir "$IMAGES_DIR/common" "$ip" "$user" "$pass_var" "$key_var" uploaded

    for role in $roles; do
      role_cloud="$(role_cloud_dir "$role")"
      upload_tar_dir "$IMAGES_DIR/$role_cloud" "$ip" "$user" "$pass_var" "$key_var" uploaded
    done

    if [[ $uploaded -eq 0 ]]; then
      err "$label 未找到可导入镜像: $IMAGES_DIR/common/*.tar 或角色镜像目录"
      return 1
    fi
  fi

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    set -e
    ctr_cmd='k3s ctr'
    if [[ \$(id -u) -ne 0 ]]; then
      ctr_cmd='sudo -n k3s ctr'
    fi

    found=0
    while IFS= read -r tar; do
      found=1
      echo \"导入: \$(basename \$tar)\"
      \$ctr_cmd images import \"\$tar\"
    done < <(find /tmp/sre-images -type f -name '*.tar' ! -name '._*.tar' | sort)
    [[ \$found -eq 1 ]] || { echo '未找到 /tmp/sre-images/*.tar' >&2; exit 1; }

    # k8s 会把短镜像名规范化为 docker.io/library/*；离线 tar 里若只有短名，
    # imagePullPolicy=Never 时需要补齐等价 tag。
    \$ctr_cmd images ls -q | while read -r tag; do
      [[ -n \"\$tag\" ]] || continue
      [[ \"\$tag\" == */* ]] && continue
      [[ \"\$tag\" == *:* ]] || continue
      \$ctr_cmd images tag --force \"\$tag\" \"docker.io/library/\$tag\" >/dev/null 2>&1 || true
    done

    rm -rf /tmp/sre-images
  "

  log "  $label 镜像导入完成"
}

fail=0
pids=()
labels=()
for role in $(unique_role_hosts); do
  import_images_for_host "$role" &
  pids+=("$!")
  labels+=("$(role_label "$role")")
done

for i in "${!pids[@]}"; do
  wait "${pids[$i]}" || { err "${labels[$i]} 镜像导入失败"; fail=1; }
done

[[ $fail -eq 1 ]] && exit 1

log "镜像导入完成"
