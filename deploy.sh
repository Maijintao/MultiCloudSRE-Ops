#!/bin/bash
set -euo pipefail

# Ctrl+C 时杀掉所有子进程（含后台 SCP/SSH）
trap 'echo ""; warn "收到中断信号，正在停止所有子进程..."; kill $(jobs -p) 2>/dev/null; wait 2>/dev/null; exit 130' INT TERM

# ============================================================
# SRE-OJ 多云靶场一键部署
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"
DEFAULT_ARTIFACT_BASE_URL="https://github.com/Maijintao/MultiCloudSRE-Ops/releases/download/deploy-artifacts-20260701"

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

  local server1_ip server1_user server1_pass
  local server2_ip server2_user server2_pass
  local server3_ip server3_user server3_pass
  local oj_ip oj_user oj_pass oj_enabled
  local images_default images_dir update_kubeconfig deploy_questions artifact_base_url

  server1_ip=$(prompt_with_default "请输入服务器1 IP" "")
  server1_user=$(prompt_with_default "请输入服务器1 SSH 用户" "root")
  server1_pass=$(prompt_password "请输入服务器1 SSH 密码")
  echo ""

  server2_ip=$(prompt_with_default "请输入服务器2 IP" "")
  server2_user=$(prompt_with_default "请输入服务器2 SSH 用户" "root")
  server2_pass=$(prompt_password "请输入服务器2 SSH 密码")
  echo ""

  server3_ip=$(prompt_with_default "请输入服务器3 IP" "")
  server3_user=$(prompt_with_default "请输入服务器3 SSH 用户" "root")
  server3_pass=$(prompt_password "请输入服务器3 SSH 密码")
  echo ""

  oj_ip=$(prompt_with_default "请输入 OJ 服务器 IP（留空则暂不部署 OJ）" "")
  if [[ -n "$oj_ip" ]]; then
    oj_user=$(prompt_with_default "请输入 OJ 服务器 SSH 用户" "root")
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
  artifact_base_url=$(prompt_with_default "请输入部署制品下载地址" "$DEFAULT_ARTIFACT_BASE_URL")

  read -r -p "是否自动合并三个服务器角色的 kubeconfig 到本机 ~/.kube/config？(Y/N) [Y]: " update_kubeconfig
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
    write_config_line "SERVER1_IP" "$server1_ip"
    write_config_line "SERVER1_USER" "$server1_user"
    write_config_line "SERVER1_PASS" "$server1_pass"
    echo "SERVER1_KEY="
    write_config_line "SERVER2_IP" "$server2_ip"
    write_config_line "SERVER2_USER" "$server2_user"
    write_config_line "SERVER2_PASS" "$server2_pass"
    echo "SERVER2_KEY="
    write_config_line "SERVER3_IP" "$server3_ip"
    write_config_line "SERVER3_USER" "$server3_user"
    write_config_line "SERVER3_PASS" "$server3_pass"
    echo "SERVER3_KEY="
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
    write_config_line "K3S_INSTALL_URL" "$artifact_base_url/install.sh"
    write_config_line "K3S_BINARY_URL" "$artifact_base_url/k3s"
    echo "K3S_BINARY_PATH="
    echo "BASE_IMAGE_BUNDLE_NAME=k3s-chaos-base-images.tar"
    write_config_line "BASE_IMAGE_ARTIFACT_URL" "$artifact_base_url/k3s-chaos-base-images.tar"
    echo "BASE_IMAGE_TAR_PATH="
    echo "IMAGE_IMPORT_MODE=local"
    write_config_line "IMAGE_ARTIFACT_BASE_URL" "$artifact_base_url"
    write_config_line "UPDATE_LOCAL_KUBECONFIG" "$update_kubeconfig"
    write_config_line "DEPLOY_QUESTIONS" "$deploy_questions"
  } > "$SCRIPT_DIR/config.env"
  chmod 600 "$SCRIPT_DIR/config.env"

  log "已生成 config.env"
}

normalize_config() {
  SERVER1_IP="${SERVER1_IP:-${ALIYUN_IP:-}}"
  SERVER1_USER="${SERVER1_USER:-${ALIYUN_USER:-root}}"
  SERVER1_PASS="${SERVER1_PASS:-${ALIYUN_PASS:-}}"
  SERVER1_KEY="${SERVER1_KEY:-${ALIYUN_KEY:-}}"

  SERVER2_IP="${SERVER2_IP:-${TENCENT_IP:-}}"
  SERVER2_USER="${SERVER2_USER:-${TENCENT_USER:-root}}"
  SERVER2_PASS="${SERVER2_PASS:-${TENCENT_PASS:-}}"
  SERVER2_KEY="${SERVER2_KEY:-${TENCENT_KEY:-}}"

  SERVER3_IP="${SERVER3_IP:-${AWS_IP:-}}"
  SERVER3_USER="${SERVER3_USER:-${AWS_USER:-root}}"
  SERVER3_PASS="${SERVER3_PASS:-${AWS_PASS:-}}"
  SERVER3_KEY="${SERVER3_KEY:-${AWS_KEY:-}}"

  OJ_ENABLED="${OJ_ENABLED:-false}"
  OJ_USER="${OJ_USER:-root}"
  OJ_PASS="${OJ_PASS:-}"
  OJ_KEY="${OJ_KEY:-}"

  # 兼容现有 manifest 占位符和旧脚本内部命名：server1/2/3 分别承载旧三角色。
  ALIYUN_IP="$SERVER1_IP"
  ALIYUN_USER="$SERVER1_USER"
  ALIYUN_PASS="$SERVER1_PASS"
  ALIYUN_KEY="$SERVER1_KEY"
  TENCENT_IP="$SERVER2_IP"
  TENCENT_USER="$SERVER2_USER"
  TENCENT_PASS="$SERVER2_PASS"
  TENCENT_KEY="$SERVER2_KEY"
  AWS_IP="$SERVER3_IP"
  AWS_USER="$SERVER3_USER"
  AWS_PASS="$SERVER3_PASS"
  AWS_KEY="$SERVER3_KEY"
}

# 加载配置
load_config() {
  if [[ ! -f "$SCRIPT_DIR/config.env" ]]; then
    init_config_interactive
  fi
  source "$SCRIPT_DIR/config.env"
  normalize_config

  # 必填校验
  local missing=0
  for var in SERVER1_IP SERVER2_IP SERVER3_IP; do
    if [[ -z "${!var}" ]]; then
      err "$var 未配置"
      missing=1
    fi
  done
  [[ $missing -eq 1 ]] && exit 1

  log "配置加载完成"
  log "  服务器1: ${SERVER1_USER}@${SERVER1_IP}"
  log "  服务器2: ${SERVER2_USER}@${SERVER2_IP}"
  log "  服务器3: ${SERVER3_USER}@${SERVER3_IP}"
  [[ "${OJ_ENABLED:-false}" == "true" ]] && log "  OJ服务器: ${OJ_USER:-root}@${OJ_IP}"

  if [[ "$SERVER1_IP" == "$SERVER2_IP" || "$SERVER1_IP" == "$SERVER3_IP" || "$SERVER2_IP" == "$SERVER3_IP" ]]; then
    warn "检测到服务器角色存在重复 IP，将按唯一服务器安装 k3s/Chaos Mesh/镜像，按角色部署服务"
  fi
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
run_step "04a" "import-base-images"
run_step "04b" "install-chaos-mesh"
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
log "靶场前端:        http://${SERVER1_IP}:31366"
if [[ "${OJ_ENABLED:-false}" == "true" ]]; then
  OJ_PORT="${OJ_PORT:-8090}"
  log "OJ 平台:         http://${OJ_IP}:${OJ_PORT}"
fi
log "Chaos Dashboard: http://${SERVER1_IP}:32333 (服务器1)"
log "                 http://${SERVER2_IP}:32333 (服务器2)"
log "                 http://${SERVER3_IP}:32333 (服务器3)"
log "访问凭据目录:    $SCRIPT_DIR/kubeconfigs/generated"
