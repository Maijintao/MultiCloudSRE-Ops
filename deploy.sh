#!/bin/bash
set -euo pipefail

# ============================================================
# SRE-OJ 多云靶场一键部署
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }

banner() {
  echo -e "${BLUE}"
  echo "  ╔══════════════════════════════════════════╗"
  echo "  ║     SRE-OJ 多云靶场 一键部署系统        ║"
  echo "  ╚══════════════════════════════════════════╝"
  echo -e "${NC}"
}

# 加载配置
load_config() {
  if [[ ! -f "$SCRIPT_DIR/config.env" ]]; then
    err "config.env 不存在，请先复制模板："
    echo "  cp config.env.example config.env"
    echo "  vim config.env"
    exit 1
  fi
  source "$SCRIPT_DIR/config.env"

  # 必填校验
  local missing=0
  for var in ALIYUN_IP TENCENT_IP AWS_IP; do
    if [[ -z "${!var}" ]]; then
      err "$var 未配置"
      missing=1
    fi
  done
  [[ $missing -eq 1 ]] && exit 1

  log "配置加载完成"
  log "  阿里云: ${ALIYUN_USER}@${ALIYUN_IP}"
  log "  腾讯云: ${TENCENT_USER}@${TENCENT_IP}"
  log "  AWS:    ${AWS_USER}@${AWS_IP}"
  [[ "${OJ_ENABLED:-false}" == "true" ]] && log "  OJ:     ${OJ_USER:-root}@${OJ_IP}"
}

# 执行部署步骤
run_step() {
  local step_num="$1"
  local step_name="$2"
  local script="$SCRIPTS_DIR/${step_num}-${step_name}.sh"

  echo ""
  log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  log "步骤: $step_num - ${step_name}"
  log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if [[ ! -f "$script" ]]; then
    warn "脚本不存在: $script (跳过)"
    return 0
  fi

  source "$script"
}

# ── 主流程 ──

banner
load_config

run_step "01" "check-prerequisites"
run_step "02" "check-servers"
run_step "03" "install-k3s"
run_step "04" "install-chaos-mesh"
run_step "05" "import-images"
run_step "06" "render-manifests"
run_step "07" "deploy-services"
run_step "08" "deploy-questions"
run_step "09" "health-check"

if [[ "${OJ_ENABLED:-false}" == "true" ]]; then
  run_step "10" "deploy-oj"
fi

echo ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "部署完成！"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "前端地址:        http://${ALIYUN_IP}:31366"
log "Chaos Dashboard: http://${ALIYUN_IP}:2333 (阿里云)"
log "                 http://${TENCENT_IP}:2333 (腾讯云)"
log "                 http://${AWS_IP}:2333 (AWS)"
