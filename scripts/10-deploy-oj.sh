#!/bin/bash
# 10 - OJ 系统部署（预留）
# 当 config.env 中 OJ_ENABLED=true 时由 deploy.sh 调用

if [[ -z "${OJ_IP:-}" ]]; then
  err "OJ_ENABLED=true 但 OJ_IP 未配置"
  exit 1
fi

log "部署在线 OJ 系统到 ${OJ_IP}..."

# TODO: 实现 OJ 部署逻辑
# 预期步骤：
# 1. SSH 连接 OJ 服务器
# 2. 安装依赖（Docker / k3s）
# 3. 部署 OJ Web 应用
# 4. 导入题目元数据（case.json / rubrics.json）
# 5. 配置 OJ ↔ 三云靶场的 IP 映射
# 6. 初始化学生账号
# 7. 验证 OJ 可访问性

warn "OJ 部署脚本尚未实现，请在 oj/ 目录中添加部署文件后完善此脚本"
