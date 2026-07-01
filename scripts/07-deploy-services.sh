#!/bin/bash
# 07 - kubectl apply 到三台服务器

log "部署 K8s 资源到三台服务器..."

deploy_to() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5" cloud="$6"

  local rendered_dir="$SCRIPT_DIR/rendered"

  # 上传 namespace
  if [[ -f "$rendered_dir/namespaces.yaml" ]]; then
    scp_upload "$rendered_dir/namespaces.yaml" "$ip" "$user" "$pass_var" "$key_var" "/tmp/namespace.yaml"
  fi

  # 上传渲染后的 manifest
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "mkdir -p /tmp/seat-1-manifests"
  for f in "$rendered_dir/$cloud/"*.yaml; do
    [[ -f "$f" ]] || continue
    scp_upload "$f" "$ip" "$user" "$pass_var" "$key_var" "/tmp/seat-1-manifests/"
  done

  # apply
  local sudo_prefix=""
  [[ "$user" != "root" ]] && sudo_prefix="sudo -n "

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    # 先创建 namespace
    if [[ -f /tmp/namespace.yaml ]]; then
      ${sudo_prefix}k3s kubectl apply -f /tmp/namespace.yaml
    fi

    # apply 所有资源
    for f in /tmp/seat-1-manifests/*.yaml; do
      [[ -f \$f ]] || continue
      echo \"apply: \$(basename \$f)\"
      ${sudo_prefix}k3s kubectl apply -f \$f
    done

    # 清理临时文件
    rm -rf /tmp/seat-1-manifests /tmp/namespace.yaml
  "

  log "  $label 资源部署完成"
}

deploy_to "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" "阿里云" "aliyun"
deploy_to "$TENCENT_IP" "$TENCENT_USER" "TENCENT_PASS" "TENCENT_KEY" "腾讯云" "tencent"
deploy_to "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" "AWS" "aws"

# 等待所有 Pod 就绪
log "等待所有 Pod 就绪..."
wait_for_pods "aliyun" "seat-1" 300
wait_for_pods "tencent" "seat-1" 300
wait_for_pods "aws" "seat-1" 300

log "服务部署完成"
