# SRE-OJ 多云靶场与 OJ 平台

本仓库现在包含两部分：

- **三云靶场一键部署**：在阿里云、腾讯云、AWS 三台服务器上部署 k3s、Chaos Mesh、跨云电商 demo、访问凭据。
- **AIOps OJ Platform**：轻量级 Python/SQLite OJ 平台，用于提交 Prompt/Skill、运行 Hermes 诊断、调用 OpenAI-compatible 评分接口打分。

真实比赛题、云主机地址、SSH 密码、kubeconfig、API key、隐藏答案、运行数据库和实验状态不要提交进仓库。

## 三云靶场快速开始

```bash
chmod +x deploy.sh
./deploy.sh

# 也可以手动复制配置模板并填写
cp config.env.example config.env
vim config.env
# 如果镜像 tar 不放在本仓库，配置 IMAGES_DIR 指向外部目录
# 例如：IMAGES_DIR=/Users/Mai/Desktop/multicloud-ops/images

./deploy.sh
```

### 三云角色

| 云 | 角色 | 部署的服务 | NodePort |
|---|---|---|---|
| 阿里云 | 流量入口 | frontend, checkout, recommendation, ad, shipping, mysql, orderstore, redis-cart | 31366, 31380, 32366, 30051 |
| 腾讯云 | 数据层 | cart, currency, email, gateway, productcatalog, redis-cart | 30007-30010, 30076 |
| AWS | 履约链 | orderservice, payment, inventory, riskcontrol, notification, userbehavior | 30051, 30070-30074 |

### 访问凭据

部署完成后会自动生成：

- `kubeconfigs/generated/aliyun-readonly.kubeconfig`
- `kubeconfigs/generated/aliyun-injector.kubeconfig`
- `kubeconfigs/generated/aliyun-chaos-dashboard.token`
- 腾讯云、AWS 同名文件

默认会把三云 readonly/injector context 合并进本机 `~/.kube/config`，可通过 `UPDATE_LOCAL_KUBECONFIG=false` 关闭。题目 inject/recover 脚本默认不部署，需要时显式设置 `DEPLOY_QUESTIONS=true`。

### 三云环境要求

- 本机：`sshpass`、`kubectl`、`ssh`
- 服务器：Ubuntu 22.04/24.04 amd64，至少 2G RAM、30G 磁盘
- 服务器安全组需放行业务 NodePort 端口 TCP 入站
- 如需本机直接使用生成的 kubeconfig，还需放行三台服务器 `6443/tcp`

## OJ 平台快速开始

需要 Python 3.10 或更新版本。

```bash
python -m unittest discover -s tests -v
node scripts/check-frontend-modules.js
PORT=8090 python server.py
```

然后打开：

```text
http://127.0.0.1:8090/
```

开发环境默认账号仅适合本机调试：

- 用户名：`admin`
- 密码：`dev-admin-password`
- 注册邀请码：`dev-invite-code`

公开网络或多人共享环境必须设置 `OJ_ENV=production`，并显式配置管理员密码、注册邀请码、JWT secret 和评分 API。

### OJ 生产环境最低配置

```bash
OJ_ENV=production
OJ_ADMIN_USERNAME=admin
OJ_ADMIN_PASSWORD=<long-random-password>
OJ_REGISTRATION_INVITE_CODE=<private-invite-code>
OJ_JWT_SECRET=<long-random-secret>
OJ_GRADER_BASE_URL=https://api.example.com/v1
OJ_GRADER_MODEL=<grader-model>
OJ_GRADER_API_KEY=<grader-key>
OJ_HERMES_DOCKER=1
OJ_HERMES_DOCKER_IMAGE=hermes-agent:latest
```

`.env.example` 是完整环境变量参考。平台不会自动读取 `.env`，请由 shell、systemd 或容器运行时加载。

## 目录结构

```text
deploy.sh                 三云靶场一键部署入口
config.env.example        三云靶场配置模板
scripts/                  三云部署脚本 + OJ 前端检查脚本
manifests/                三云 K8s 资源模板
kubeconfigs/              三云 RBAC + kubeconfig 模板
oj_platform/              OJ 后端 Python 模块
static/                   OJ 前端入口、样式和静态资源
faults/                   OJ 脱敏 demo case 和故障脚本
runtime/                  可选 MCP 辅助运行时
docs/                     OJ 架构、部署、题目格式、安全和发布文档
tests/                    OJ 单元测试和开源卫生检查
```

## OJ 文档

- [架构说明](docs/architecture.md)
- [题目格式](docs/case-format.md)
- [部署说明](docs/deployment.md)
- [安全说明](docs/security.md)
- [前端模块说明](docs/frontend-build.md)
- [发布说明](docs/release.md)

## 许可证

MIT
