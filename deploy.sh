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

prompt_with_default() {
  local prompt="$1"
  local default="$2"
  local value

  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " value
    echo "${value:-$default}"
  else
    read -r -p "$prompt: " value
    echo "$value"
  fi
}

prompt_password() {
  local prompt="$1"
  local value
  read -r -s -p "$prompt: " value
  printf "\n" >&2
  printf "%s\n" "$value"
}

shell_quote() {
  printf "%q" "$1"
}

write_config_line() {
  local key="$1"
  local value="$2"
  printf "%s=%s\n" "$key" "$(shell_quote "$value")"
}

init_config_interactive() {
  if [[ ! -t 0 ]]; then
    err "config.env 不存在，且当前不是交互式终端，无法询问服务器信息"
    echo "  请先运行: ./deploy.sh"
    echo "  或手动复制: cp config.env.example config.env"
    exit 1
  fi

  warn "config.env 不存在，将进入交互式配置向导"
  echo ""

  local aliyun_ip aliyun_user aliyun_pass
  local tencent_ip tencent_user tencent_pass
  local aws_ip aws_user aws_pass
  local oj_enabled oj_ip oj_user oj_pass
  local images_default images_dir update_kubeconfig deploy_questions

  aliyun_ip=$(prompt_with_default "请输入阿里云 IP" "")
  aliyun_user=$(prompt_with_default "请输入阿里云 SSH 用户" "root")
  aliyun_pass=$(prompt_password "请输入阿里云 SSH 密码")
  echo ""

  tencent_ip=$(prompt_with_default "请输入腾讯云 IP" "")
  tencent_user=$(prompt_with_default "请输入腾讯云 SSH 用户" "root")
  tencent_pass=$(prompt_password "请输入腾讯云 SSH 密码")
  echo ""

  aws_ip=$(prompt_with_default "请输入 AWS IP" "")
  aws_user=$(prompt_with_default "请输入 AWS SSH 用户" "root")
  aws_pass=$(prompt_password "请输入 AWS SSH 密码")
  echo ""

  read -r -p "是否部署第 4 台 OJ 服务器？(Y/N) [N]: " oj_enabled
  oj_enabled="${oj_enabled:-N}"
  if [[ "$oj_enabled" =~ ^[Yy]$ ]]; then
    oj_ip=$(prompt_with_default "请输入 OJ 服务器 IP" "")
    oj_user=$(prompt_with_default "请输入 OJ SSH 用户" "root")
    oj_pass=$(prompt_password "请输入 OJ SSH 密码")
    oj_enabled="true"
  else
    oj_enabled="false"
    oj_ip=""
    oj_user=""
    oj_pass=""
  fi
  echo ""

  images_default="$SCRIPT_DIR/images"
  if [[ -d "/Users/Mai/Desktop/multicloud-ops/images" ]]; then
    images_default="/Users/Mai/Desktop/multicloud-ops/images"
  fi
  images_dir=$(prompt_with_default "请输入离线镜像目录" "$images_default")

  read -r -p "是否自动合并三云 kubeconfig 到本机 ~/.kube/config？(Y/N) [Y]: " update_kubeconfig
  update_kubeconfig="${update_kubeconfig:-Y}"
  if [[ "$update_kubeconfig" =~ ^[Yy]$ ]]; then
    update_kubeconfig="true"
  else
    update_kubeconfig="false"
  fi

  read -r -p "是否部署题目 inject/recover 脚本？(Y/N) [N]: " deploy_questions
  deploy_questions="${deploy_questions:-N}"
  if [[ "$deploy_questions" =~ ^[Yy]$ ]]; then
    deploy_questions="true"
  else
    deploy_questions="false"
  fi

  {
    echo "#!/bin/bash"
    echo "# 由 ./deploy.sh 交互式生成"
    write_config_line "ALIYUN_IP" "$aliyun_ip"
    write_config_line "ALIYUN_USER" "$aliyun_user"
    write_config_line "ALIYUN_PASS" "$aliyun_pass"
    echo "ALIYUN_KEY="
    write_config_line "TENCENT_IP" "$tencent_ip"
    write_config_line "TENCENT_USER" "$tencent_user"
    write_config_line "TENCENT_PASS" "$tencent_pass"
    echo "TENCENT_KEY="
    write_config_line "AWS_IP" "$aws_ip"
    write_config_line "AWS_USER" "$aws_user"
    write_config_line "AWS_PASS" "$aws_pass"
    echo "AWS_KEY="
    write_config_line "OJ_ENABLED" "$oj_enabled"
    write_config_line "OJ_IP" "$oj_ip"
    write_config_line "OJ_USER" "$oj_user"
    write_config_line "OJ_PASS" "$oj_pass"
    echo "OJ_KEY="
    echo "APM_ENABLED=false"
    echo "APM_ENDPOINT="
    echo "APM_TOKEN="
    echo "SKIP_K3S_INSTALL=false"
    echo "SKIP_CHAOS_MESH=false"
    echo "SKIP_IMAGE_IMPORT=false"
    echo "SKIP_ACCESS_GENERATION=false"
    write_config_line "IMAGES_DIR" "$images_dir"
    write_config_line "UPDATE_LOCAL_KUBECONFIG" "$update_kubeconfig"
    write_config_line "DEPLOY_QUESTIONS" "$deploy_questions"
  } > "$SCRIPT_DIR/config.env"
  chmod 600 "$SCRIPT_DIR/config.env"

  log "已生成 config.env"
}

# 加载配置
load_config() {
  if [[ ! -f "$SCRIPT_DIR/config.env" ]]; then
    init_config_interactive
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

source "$SCRIPTS_DIR/lib.sh"

run_step "01" "check-prerequisites"
run_step "02" "check-servers"
run_step "03" "install-k3s"
run_step "04" "install-chaos-mesh"
run_step "05" "import-images"
run_step "06" "render-manifests"
run_step "07" "deploy-services"
run_step "08" "generate-access"

if [[ "${DEPLOY_QUESTIONS:-false}" == "true" ]]; then
  run_step "08" "deploy-questions"
else
  log "DEPLOY_QUESTIONS=false, 跳过题目 inject/recover 脚本部署"
fi

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
log "访问凭据目录:    $SCRIPT_DIR/kubeconfigs/generated"
