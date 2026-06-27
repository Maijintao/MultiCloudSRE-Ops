#!/bin/bash
# 01 - 检查本机依赖工具

log "检查本机依赖..."

local_deps=(sshpass ssh scp kubectl)
local_missing=0

for dep in "${local_deps[@]}"; do
  if command -v "$dep" &>/dev/null; then
    log "  $dep: $(command -v $dep)"
  else
    err "  $dep: 未安装"
    local_missing=1
  fi
done

if [[ $local_missing -eq 1 ]]; then
  err "缺少依赖，请先安装："
  echo "  brew install sshpass kubectl   # macOS"
  echo "  apt install sshpass kubectl    # Ubuntu"
  exit 1
fi

log "本机依赖检查通过"
