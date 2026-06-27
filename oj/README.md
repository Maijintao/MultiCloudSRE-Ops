# 在线 OJ 系统（预留）

## 概述

OJ（Online Judge）系统作为第 4 台服务器独立部署，通过 config.env 中的 `OJ_ENABLED=true` 启用。

## 预期功能

- 题目展示与管理（从 questions/ 加载）
- 学生答题界面（提交 RCA 分析报告）
- 自动评分（调用 rubrics.json 评分标准）
- 故障注入触发（调用靶机的 inject.sh）
- 恢复与验收（调用 recover.sh + 验证脚本）

## 目录结构

```
oj/
├── manifests/          # OJ 应用部署文件（Docker Compose / K8s）
├── config.env.example  # OJ 特定配置
├── init-scripts/       # 初始化脚本（题目导入、账号创建）
└── integration/        # OJ ↔ 靶场集成层
    ├── inject-callback.sh    # 注入完成后通知 OJ
    ├── verify-callback.sh    # 验收完成后通知 OJ
    └── kubeconfig-setup.sh   # 为 OJ 配置三云 kubeconfig
```

## 与靶场的集成

OJ 系统通过以下方式与三云靶场交互：

1. **kubeconfig**: 使用 `kubeconfigs/` 中的注入权限 kubeconfig 连接三台 k3s
2. **inject.sh**: OJ 通过 SSH 在对应靶机上执行故障注入
3. **recover.sh**: OJ 在答题结束后执行恢复
4. **健康检查**: OJ 定期调用 health-check 确认靶场可用

## 待实现

- [ ] 确定 OJ 技术栈（Docker Compose / K8s）
- [ ] OJ Web 应用部署 manifest
- [ ] 题目元数据导入脚本
- [ ] 学生账号管理
- [ ] 评分引擎集成
