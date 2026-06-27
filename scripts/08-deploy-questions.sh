#!/bin/bash
# 08 - 上传出题/恢复脚本到各台服务器

QUESTIONS_DIR="$SCRIPT_DIR/../questions"

if [[ ! -d "$QUESTIONS_DIR" ]] || [[ -z "$(ls -A "$QUESTIONS_DIR" 2>/dev/null)" ]]; then
  warn "questions/ 目录为空，跳过题目部署"
  return 0 2>/dev/null || exit 0
fi

log "上传出题脚本到三台服务器..."

upload_questions_to() {
  local ip="$1" user="$2" pass_var="$3" key_var="$4" label="$5"

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "mkdir -p /opt/sre-questions"

  # 打包题目目录上传
  local tar_file="/tmp/sre-questions.tar.gz"
  tar -czf "$tar_file" -C "$SCRIPT_DIR/.." questions/

  scp_upload "$tar_file" "$ip" "$user" "$pass_var" "$key_var" "/tmp/sre-questions.tar.gz"
  rm -f "$tar_file"

  ssh_exec "$ip" "$user" "$pass_var" "$key_var" "
    cd /opt && tar -xzf /tmp/sre-questions.tar.gz
    chmod +x /opt/sre-questions/questions/**/inject.sh 2>/dev/null
    chmod +x /opt/sre-questions/questions/**/recover.sh 2>/dev/null
    rm -f /tmp/sre-questions.tar.gz
    echo '题目数量: '\$(find /opt/sre-questions/questions -name 'case.json' | wc -l)
  "

  log "  $label 题目上传完成"
}

upload_questions_to "$ALIYUN_IP" "$ALIYUN_USER" "ALIYUN_PASS" "ALIYUN_KEY" "阿里云"
upload_questions_to "$TENCENT_IP" "$TENCENT_USER" "TENCENT_PASS" "TENCENT_KEY" "腾讯云"
upload_questions_to "$AWS_IP" "$AWS_USER" "AWS_PASS" "AWS_KEY" "AWS"

log "题目部署完成"
