# 安全说明

平台会运行选手提供的 Prompt 和可选 Skill 内容，应当按“不可信输入执行系统”来部署。

## 生产环境必填项

设置 `OJ_ENV=production` 后，以下环境变量必须显式提供：

- `OJ_ADMIN_PASSWORD`
- `OJ_REGISTRATION_INVITE_CODE`
- `OJ_JWT_SECRET`
- `OJ_GRADER_BASE_URL`
- `OJ_GRADER_MODEL`
- `OJ_GRADER_API_KEY`

开发默认值只适合本机调试。服务启动时会打印开发模式 warning，不要把开发默认值暴露到
公网或多人共享环境。

## 仓库卫生

不要提交以下内容：

- `.env` 或真实进程环境文件。
- SQLite 数据库、`state/` 运行状态、日志和临时文件。
- SSH key、kubeconfig、token、API key 或云厂商凭据。
- 绑定真实实验环境的公网 IP、主机名或账号。
- 私有比赛题的 `ideal-answer.json`、`rubrics.json` 和故障脚本。

测试套件包含开源卫生检查，用来扫描常见泄漏形态。但它不能替代发布前人工检查
`git diff` 和 `git status`。

## 运行隔离

当选手不可信时，建议开启 Hermes Docker 隔离。容器中只挂载本次运行所需的 run home、
空 workspace、Prompt、runner、Hermes runtime 和明确允许的只读 secret。

## 管理员配置

管理员界面可以保存平台评分 API。保存时平台只展示脱敏 key，但数据库仍会保存真实 key，
因此 `state/` 目录应按敏感数据处理并单独备份、加权限保护。
