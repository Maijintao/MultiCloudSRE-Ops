#!/bin/bash
# 07 - kubectl apply 到服务器角色（按唯一 IP 去重）

log "部署 K8s 资源到服务器角色..."

deploy_to() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4"
  shift 4
  local cloud_dirs=("$@")

  local rendered_dir="$SCRIPT_DIR/rendered"

  # 上传 namespace
  if [[ -f "$rendered_dir/namespaces.yaml" ]]; then
    scp_upload "$rendered_dir/namespaces.yaml" "$ip" "$user" "$pass_var" "$key_var" "/tmp/namespace.yaml"
  fi

  # 上传所有云目录的渲染后 manifest（去重后的多个角色可能共享此 IP）
  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "rm -rf /tmp/seat-1-manifests && mkdir -p /tmp/seat-1-manifests"
  for cloud in "${cloud_dirs[@]}"; do
    for f in "$rendered_dir/$cloud/"*.yaml; do
      [[ -f "$f" ]] || continue
      scp_upload "$f" "$ip" "$user" "$pass_var" "$key_var" "/tmp/seat-1-manifests/"
    done
  done

  # apply（捕获错误，不被末尾 rm 吞掉）
  local sudo_prefix=""
  if [[ "$user" != "root" ]]; then
    sudo_prefix="sudo -n "
  fi

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    deploy_fail=0

    # 先创建 namespace
    if [[ -f /tmp/namespace.yaml ]]; then
      ${sudo_prefix}k3s kubectl apply -f /tmp/namespace.yaml || deploy_fail=1
    fi

    # apply 所有资源
    for f in /tmp/seat-1-manifests/*.yaml; do
      [[ -f \$f ]] || continue
      echo \"apply: \$(basename \$f)\"
      ${sudo_prefix}k3s kubectl apply -f \$f || deploy_fail=1
    done

    # 清理临时文件
    rm -rf /tmp/seat-1-manifests /tmp/namespace.yaml

    # 如果有 apply 失败，退出码非零，触发 deploy.sh 的 set -e
    if [[ \$deploy_fail -ne 0 ]]; then
      echo 'ERROR: 部分资源 apply 失败' >&2
      exit 1
    fi
  "

  log "  ${ip} 资源部署完成 (云: ${cloud_dirs[*]})"
}

# 按唯一 IP 分组，避免同 IP 重复 SSH 部署（兼容 bash 3.x，不用 declare -A）
seen_ips=""
for role in server1 server2 server3; do
  ip="$(role_ip "$role")"
  # 检查此 IP 是否已处理
  already=0
  for seen in $seen_ips; do
    [[ "$seen" == "$ip" ]] && already=1 && break
  done
  [[ $already -eq 1 ]] && continue
  seen_ips="$seen_ips $ip"

  # 收集共享此 IP 的所有角色的云目录
  clouds=()
  roles_on_ip=""
  for r in server1 server2 server3; do
    if [[ "$(role_ip "$r")" == "$ip" ]]; then
      clouds+=("$(role_cloud_dir "$r")")
      roles_on_ip="$roles_on_ip $r"
    fi
  done

  log "  部署到 ${ip} (角色:${roles_on_ip}, 云: ${clouds[*]})"
  deploy_to \
    "$ip" \
    "$(role_user "$role")" \
    "$(role_pass_var "$role")" \
    "$(role_key_var "$role")" \
    "${clouds[@]}"
done

# 等待所有唯一主机的 Pod 就绪
log "等待所有 Pod 就绪..."
for role in $(unique_role_hosts); do
  wait_for_pods "$role" "seat-1" 300
done

log "服务部署完成"
