# 部署说明

本项目可以直接用 Python 启动，适合本地演示和小规模实验。多人共享或公开网络部署时，
请使用显式环境变量、进程管理器和 Hermes Docker 隔离。

## 本地演示

```bash
python -m unittest discover -s tests -v
node scripts/check-frontend-modules.js
PORT=8090 python server.py
```

访问：

```text
http://127.0.0.1:8090/
```

开发默认账号：

- 用户名：`admin`
- 密码：`dev-admin-password`
- 注册邀请码：`dev-invite-code`

## 生产环境最低配置

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

`.env.example` 是完整环境变量参考。平台不会自动读取 `.env`，请由 shell、systemd 或容器
运行时加载。

## 评分 API

评分 API 需要兼容 OpenAI `/chat/completions`。平台会优先使用管理员在界面中保存的评分
配置；如果数据库里没有保存配置，则回退到 `OJ_GRADER_BASE_URL`、`OJ_GRADER_MODEL` 和
`OJ_GRADER_API_KEY`。

## Systemd

示例服务文件是 `systemd/oj-platform.service`，默认假设项目部署在 `/opt/oj-platform`，
并读取 `/etc/oj-platform.env`。

```bash
cp systemd/oj-platform.service /etc/systemd/system/oj-platform.service
systemctl daemon-reload
systemctl enable --now oj-platform
```

## 运行状态

默认运行状态位于 `state/`，包括 SQLite 数据库、JWT secret 和运行中产生的临时文件。
该目录已被 Git 忽略。如果需要保留用户和提交记录，请单独备份该目录。
