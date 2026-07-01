# SRE-OJ 多云靶场一键部署包

## 概述

本部署包用于在 3 台云服务器上一键部署完整的 SRE 红蓝军靶场环境：
- **k3s** 单节点集群（每台独立）
- **Chaos Mesh** 故障注入框架
- **电商微服务 Demo**（Google Hipster Shop 改版，跨云拆分）
- **环境访问凭据**（readonly/injector kubeconfig + Chaos Dashboard token）

三台服务器各承担不同角色，合起来构成一个完整的 seat-1 电商系统。

## 快速开始

```bash
# 1. 直接运行，一路输入三云 IP、SSH 用户、密码、镜像目录
chmod +x deploy.sh
./deploy.sh

# 也可以手动复制配置模板并填写
cp config.env.example config.env
vim config.env
# 如果镜像 tar 不放在本仓库，配置 IMAGES_DIR 指向外部目录
# 例如：IMAGES_DIR=/Users/Mai/Desktop/multicloud-ops/images

# 再运行部署
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

## 访问凭据

部署完成后会自动生成：

- `kubeconfigs/generated/aliyun-readonly.kubeconfig`
- `kubeconfigs/generated/aliyun-injector.kubeconfig`
- `kubeconfigs/generated/aliyun-chaos-dashboard.token`
- 腾讯云、AWS 同名文件

默认会把三云 readonly/injector context 合并进本机 `~/.kube/config`，可通过 `UPDATE_LOCAL_KUBECONFIG=false` 关闭。题目 inject/recover 脚本默认不部署，需要时显式设置 `DEPLOY_QUESTIONS=true`。

## 环境要求

- 本机：sshpass, kubectl, ssh
- 服务器：Ubuntu 22.04/24.04 amd64, 至少 2G RAM, 30G 磁盘
- 服务器安全组需放行上表中的 NodePort 端口（TCP 入站）
- 如需本机直接使用生成的 kubeconfig，还需放行三台服务器 `6443/tcp`

## 在线 OJ 系统

OJ 系统仍是预留模块，不属于当前三云环境一键部署闭环。
