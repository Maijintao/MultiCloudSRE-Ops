# SRE-OJ 多云靶场一键部署包

## 概述

本部署包用于在 3 台云服务器上一键部署完整的 SRE 红蓝军靶场环境：
- **k3s** 单节点集群（每台独立）
- **Chaos Mesh** 故障注入框架
- **电商微服务 Demo**（Google Hipster Shop 改版，跨云拆分）

三台服务器各承担不同角色，合起来构成一个完整的 seat-1 电商系统。

## 快速开始

```bash
# 1. 复制配置模板并填写
cp config.env.example config.env
vim config.env

# 2. 一键部署
chmod +x deploy.sh
./deploy.sh
```

## 服务器角色

| 云 | 角色 | 部署的服务 | NodePort |
|---|---|---|---|
| 阿里云 | 流量入口 | frontend, checkout, recommendation, ad, shipping, mysql, orderstore, redis-cart | 31366, 31380, 32366, 30051 |
| 腾讯云 | 数据层 | cart, currency, email, gateway, productcatalog, redis-cart | 30007-30010, 30076 |
| AWS | 履约链 | orderservice, payment, inventory, riskcontrol, notification, userbehavior | 30051, 30070-30074 |

## 目录结构

```
├── deploy.sh              # 一键部署入口
├── config.env.example     # 配置模板
├── scripts/               # 部署子脚本
├── manifests/             # K8s 资源模板（含 IP 占位符）
├── images/                # 离线镜像 tar
├── questions/             # 题库（56题，14分类）
├── kubeconfigs/           # RBAC + kubeconfig 模板
├── oj/                    # 在线 OJ 系统（预留）
└── rendered/              # 运行时渲染输出（自动生成）
```

## 环境要求

- 本机：sshpass, kubectl, ssh
- 服务器：Ubuntu 22.04/24.04 amd64, 至少 2G RAM, 30G 磁盘
- 服务器安全组需放行上表中的 NodePort 端口（TCP 入站）

## 在线 OJ 系统

OJ 系统作为可选的第 4 台服务器部署，详见 `oj/README.md`。
设置 `OJ_ENABLED=true` 后 deploy.sh 会自动部署。
