#!/bin/bash
# 06 - 用 sed 渲染模板，替换 IP 占位符

log "渲染 K8s manifest 模板..."

RENDERED_DIR="$SCRIPT_DIR/rendered"
MANIFESTS_DIR="$SCRIPT_DIR/manifests"

mkdir -p "$RENDERED_DIR/aliyun" "$RENDERED_DIR/tencent" "$RENDERED_DIR/aws"

# 清理旧渲染文件
rm -rf "$RENDERED_DIR/aliyun/"* "$RENDERED_DIR/tencent/"* "$RENDERED_DIR/aws/"*

render_cloud() {
  local cloud="$1"
  local src_dir="$MANIFESTS_DIR/$cloud"
  local dst_dir="$RENDERED_DIR/$cloud"

  if [[ ! -d "$src_dir" ]]; then
    warn "模板目录不存在: $src_dir"
    return 0
  fi

  mkdir -p "$dst_dir"

  for f in "$src_dir/"*.yaml; do
    [[ -f "$f" ]] || continue
    local basename="$(basename "$f")"
    sed \
      -e "s/__ALIYUN_IP__/${ALIYUN_IP}/g" \
      -e "s/__TENCENT_IP__/${TENCENT_IP}/g" \
      -e "s/__AWS_IP__/${AWS_IP}/g" \
      "$f" > "$dst_dir/$basename"
    log "  渲染: $cloud/$basename"
  done
}

# 渲染 namespace（三台共用）
sed \
  -e "s/__ALIYUN_IP__/${ALIYUN_IP}/g" \
  -e "s/__TENCENT_IP__/${TENCENT_IP}/g" \
  -e "s/__AWS_IP__/${AWS_IP}/g" \
  "$MANIFESTS_DIR/namespaces.yaml" > "$RENDERED_DIR/namespaces.yaml" 2>/dev/null || true

# 渲染各云 manifest
render_cloud "aliyun"
render_cloud "tencent"
render_cloud "aws"

# 如果启用 APM，额外注入 APM 环境变量
if [[ "${APM_ENABLED:-false}" == "true" ]]; then
  log "APM 已启用，注入 APM 配置..."
  for cloud in aliyun tencent aws; do
    for f in "$RENDERED_DIR/$cloud/"*-deploy.yaml; do
      [[ -f "$f" ]] || continue
      sed -i '' \
        -e "s/__APM_ENDPOINT__/${APM_ENDPOINT}/g" \
        -e "s/__APM_TOKEN__/${APM_TOKEN}/g" \
        "$f" 2>/dev/null || true
    done
  done
fi

log "模板渲染完成 → rendered/"
