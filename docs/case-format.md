# 题目格式

每道题通常放在 `faults/<case-id>/` 下。

```text
case.json
ideal-answer.json
rubrics.json
inject.sh
recover.sh
```

其中 `case.json` 是面向选手的公开题面；其它文件是服务端评分和运维材料。真实比赛中，
隐藏答案、评分点和真实故障脚本建议保存在私有仓库或私有部署环境中。

平台只会把存在 `case.json` 的目录当作题目加载。只有 `inject.sh` / `recover.sh` 的目录
可以作为脚本参考或题目草稿，但不会出现在题目列表中。

## `case.json`

常用字段：

- `id`：稳定题目 ID，建议与目录名一致。
- `title`：短标题。
- `fault_phenomenon`：选手可见的故障现象。
- `public_case_info`：公开环境说明和可用工具提示。
- `order_id`：展示排序。
- `inject_script`：答题前执行的故障注入脚本路径。
- `recover_script`：答题后执行的恢复脚本路径。
- `submission_enabled`：是否允许选手直接提交该题。
- `ai_analysis_visible`：是否允许选手查看 AI 分析内容。
- `case_set_id`：所属题目分组，常用值有 `training`、`ungrouped` 或 `test-set-*`。
- `mcp_servers`：该题运行时可用的 MCP 列表；这是运行配置，不应在题面里泄漏私有结论。

## 测试集

`config.json` 中的 `test_sets` 定义测试集。每个测试集可以配置：

- `id`
- `name`
- `order_id`
- `submission_enabled`
- `mcp_servers`

选手提交测试集时，平台会对测试集内题目生成一组提交，并把测试集的 MCP 选择快照写入
每条提交，避免后续配置变化影响历史提交。

## 私有评分文件

`ideal-answer.json` 描述期望诊断结果；`rubrics.json` 描述正向和负向评分点。开源 demo
可以保留示例答案用于说明格式；正式比赛题不要把真实答案和评分点放入公开仓库。

## 脚本

`inject.sh` 和 `recover.sh` 在 OJ 主机上执行。demo 脚本使用 `faults/lib.sh`：

- 未配置 `FAULT_TARGET_HOST` 时，在本机 `VOTING_APP_DIR` 下执行命令。
- 配置 `FAULT_TARGET_HOST` 时，通过 SSH 在远端执行命令。

脚本应尽量满足：

- 幂等，可重复执行。
- 有明确超时和错误处理。
- 不包含真实凭据。
- 避免无必要的破坏性操作。
