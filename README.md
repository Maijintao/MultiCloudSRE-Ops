# AIOps OJ Platform

AIOps OJ Platform 是一个轻量级的 AIOps 故障诊断评测平台，用 Python、
SQLite 和原生浏览器前端实现。它适合做 Prompt、Skill、MCP 工具使用能力
和运维诊断流程的实验评测。

平台的基本流程是：选手提交 Prompt、模型连接配置和可选 Skills；后台 worker
为每次提交创建隔离运行环境，调用 Hermes 完成一次无人值守诊断；最后把结构化
答案和过程摘要发送到 OpenAI-compatible 评分接口，由平台统一评分。

这个仓库是脱敏后的开源版本，只包含平台代码和少量公开 demo case。真实比赛题、
云主机地址、凭据、隐藏答案、运行数据库和实验状态不应进入公开仓库。

## 功能特性

- 基于 SQLite 的用户、提交、配置和评分状态存储。
- 单后台 worker 顺序领取提交，避免多个故障注入任务互相干扰。
- 每次提交独立生成 Hermes 运行目录，支持 Docker 隔离。
- 支持选手提交文本 Skill 或 ZIP Skill 包。
- 支持平台托管的评分 API 配置，管理员可以在界面中检查并保存评分接口。
- 支持按题目或测试集选择可用 MCP 工具。
- 提交详情页实时展示运行日志、工具调用、最终答案和评分结果。
- 前端使用无依赖的原生 ES Modules，不需要打包器。

## 目录结构

```text
oj_platform/              后端 Python 模块
static/                   前端入口、样式和静态资源
static/app/               原生 ES Module 前端源码
faults/                   脱敏 demo case 和故障脚本
runtime/                  可选的只读 MCP 辅助运行时
scripts/check-frontend-modules.js
tests/                    单元测试和开源卫生检查
docs/                     架构、部署、题目格式和发布文档
```

## 快速开始

需要 Python 3.10 或更新版本。

```bash
cd aiops-platform
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

如果要部署到公开网络或多人共享环境，必须设置 `OJ_ENV=production`，并显式配置
管理员密码、注册邀请码、JWT secret 和评分 API。

## 配置

复制 `.env.example` 到你的部署环境中，并通过 shell、systemd、容器运行时或进程
管理器加载。平台不会自动读取 `.env` 文件。

生产环境至少需要配置：

- `OJ_ADMIN_PASSWORD`
- `OJ_REGISTRATION_INVITE_CODE`
- `OJ_JWT_SECRET`
- `OJ_GRADER_BASE_URL`
- `OJ_GRADER_MODEL`
- `OJ_GRADER_API_KEY`

评分接口需要兼容 OpenAI 的 `/chat/completions` API。也可以在管理员界面中检查并
保存平台评分 API，保存后的配置会写入数据库并优先于环境变量使用。

选手模型接口由用户在个人资料页配置，平台只保存脱敏后的 key 展示值，提交运行时
会按当前配置生成快照。

## 前端开发

前端直接使用浏览器原生 ES Modules：

- 入口文件：`static/app/main.js`
- 页面入口：`static/index.html`
- 样式文件：`static/styles.css`

修改前端后运行：

```bash
node scripts/check-frontend-modules.js
```

该脚本会检查 `static/index.html` 是否加载 `static/app/main.js`，并防止回退到旧的
`static/app.js` bundle、全局 `window.OJApp` 注册表或内联事件属性。

## Demo Cases

公开仓库保留了三个带 `case.json` 的 Example Voting App 方向脱敏 demo：

- `db_down`
- `redis_down`
- `worker_down`

这些 case 用于展示题目结构和评分流程。真实比赛题、私有评分点、真实云环境地址、
SSH key、kubeconfig、API key 和运行数据库都不要提交到公开仓库。

`faults/` 下也可能包含只有 `inject.sh` / `recover.sh` 的脚本型实验材料。没有
`case.json` 的目录不会被平台当作题目加载，只适合作为故障脚本参考或后续私有题目草稿。

## Docker Runtime

Hermes 运行镜像可以这样构建：

```bash
docker build -t hermes-agent:latest -f docker/hermes-runtime.Dockerfile .
```

如需指定 apt 镜像源，可以显式传入：

```bash
docker build --build-arg APT_MIRROR=https://mirror.example.org -t hermes-agent:latest -f docker/hermes-runtime.Dockerfile .
```

## 文档

- [架构说明](docs/architecture.md)
- [题目格式](docs/case-format.md)
- [部署说明](docs/deployment.md)
- [安全说明](docs/security.md)
- [前端模块说明](docs/frontend-build.md)
- [发布说明](docs/release.md)

## 许可证

MIT
