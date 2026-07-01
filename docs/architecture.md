# 架构说明

AIOps OJ Platform 的结构刻意保持简单：后端是 `oj_platform/` 下的一组
Python 模块，前端是 `static/` 下的静态 HTML、CSS 和原生 ES Modules，运行状态
存储在 SQLite 中。

## 运行流程

1. 用户登录平台，并在个人资料页配置答题模型。
2. 用户选择单题或测试集，提交 Prompt、Skills 和可选 MCP 选择。
3. 后台 worker 从队列中领取一条提交。
4. 如果题目配置了 `inject.sh`，worker 会先执行故障注入脚本。
5. 平台为 Hermes 创建独立运行目录、workspace、Prompt 文件、模型配置和 Skill 目录。
6. Hermes 无人值守运行，过程日志、工具调用和最终答案持续写入提交详情。
7. 如果题目配置了 `recover.sh`，worker 会在答题阶段后执行恢复脚本。
8. 平台把最终答案和压缩后的过程摘要发送到 OpenAI-compatible 评分接口。
9. 评分结果写回提交记录，并在前端展示。

## 主要模块

- `server.py`：初始化数据库、恢复中断提交、启动 worker 并提供 HTTP 服务。
- `oj_platform/http_app.py`：处理 API 路由和静态文件。
- `oj_platform/worker.py`：实现提交状态机。
- `oj_platform/hermes_runner.py`：构造 Hermes 本地运行命令并记录过程。
- `oj_platform/hermes_docker.py`：构造 Docker 隔离运行命令。
- `oj_platform/cases.py`：读取、校验、编辑题目和测试集。
- `oj_platform/grader_config.py`：管理平台托管评分 API 配置。
- `oj_platform/grading_api.py`：调用评分接口并处理流式评分输出。
- `oj_platform/mcp.py`：管理平台可用 MCP 名称、公开选项和每次提交的 MCP 快照。

## 前端结构

前端入口是 `static/app/main.js`。各模块通过浏览器原生 `import` 互相引用，不再生成
`static/app.js` bundle。`scripts/check-frontend-modules.js` 用于检查模块入口、导入后缀、
全局注册表和内联事件等约束。

## 数据边界

公开题面只应暴露 `case.json` 中的公共字段。`ideal-answer.json`、`rubrics.json`、
真实故障脚本、运行数据库和云环境配置都属于服务端或私有比赛材料。开源仓库中只保留
可以公开展示的 demo 内容。
