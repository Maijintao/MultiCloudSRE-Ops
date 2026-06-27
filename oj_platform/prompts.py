import json

from .cases import resolve_case_script
from .hermes_transcript import answer_process_for_api_grading


GRADING_SYSTEM_PROMPT = """
你是一个严格、公正的 AIOps 云服务故障诊断评测裁判。

你的任务是根据题目的标准答案、评分规则和选手 Agent 的最终输出，对选手输出进行评分。

你必须遵守以下原则：

1. 不要假设选手做过但没有写出的内容。
2. 允许同义表达。只要选手表达的技术含义与标准答案一致，应视为正确。
3. 不要求选手逐字匹配标准答案，但要求根因、证据、因果链、验证方法和修复建议在技术上成立。
4. 区分“根因”和“表面现象”。只描述页面不可用、接口失败、服务异常，不能算准确根因。
5. 只把选手过程输出中实际成功返回的工具结果视为已执行证据。执行失败、被拒绝、计划以后执行的命令，以及最终答案自行复述的数值都不能作为证据。
6. “独立证据”必须分别直接支撑关键机制。错误码、容器存活、容量正常等后果或排除项，不能充当配置不匹配、索引缺失、周期性 GC 等具体根因的第二类直接证据。
7. 严格区分观测事实与推断。没有配置、抓包、数据库执行计划或时间序列时，不得把推断描述成已经验证的事实。
""".strip()


GRADING_USER_PROMPT_TEMPLATE = """
请你对下面这个 AIOps 故障诊断题的选手输出进行评分。

# 一、题目信息

## 题面

{{case.json}}

## 故障注入脚本

{{inject.sh}}

## 故障恢复脚本

{{recover.sh}}

# 二、标准答案

{{ideal-answer.json}}

# 三、选手 Agent 最终输出

{{CONTESTANT_OUTPUT}}

# 四、选手 Agent 过程输出

{{CONTESTANT_PROCESS}}

# 五、Rubrics

{{rubrics.json}}

# 六、最高分限制规则

评分时必须应用以下最高分限制：

- 如果输出过程或结果完全偏离，没有有效诊断，总分最高 10 分。
- 如果修复建议包含危险操作，总分最高 10 分。
- 如果没有定位根因或根因定位错误，总分最高 70 分。
- 如果证据与结论明显矛盾，总分最高 70 分。
- 如果存在明显编造证据，总分最高 70 分。
- 如果 Rubric 明确要求主动复现、时间序列、数据库侧执行计划或端到端业务验证，而选手只在最终答案中提出以后应执行这些验证，对应 Rubric 必须判定为未命中。
- 如果关键诊断命令执行失败，除非另有 Rubric 明确认可的等价直接证据，否则不得根据选手最终答案中的同名结论补记为成功证据。

# 七、评分说明

- 必须根据 Rubrics 来评分，且对于每条 rubric，只有命中和未命中，不能判定为部分命中
- 逐条核对过程输出中的工具返回值后再判断证据 Rubric；不得只根据最终答案的 key_evidence 列表判定命中
- 多个字段来自同一次日志输出时仍属于同一数据源；多个与根因无关的排除项不能凑成“多源交叉验证”
- 对最终分数进行归一化处理，即最终得分 = max(0, 命中正分 + 命中负分) × 100 / positive_points_total，其中，除法向下取整。最终分数必须是介于 0 到 100 分的整数，填入到输出 json 的 `total_score` 字段中。
- 输出的分数相关字段中，除了 `total_score` 字段为归一化后的结果，其余分数均为原始分
- 选手 Agent 过程输出中 Tool calls: 后面每一项为一次工具调用，所有 Tool calls: 后面的 item 数量之和为总工具调用次数
- 参考答案未描述清楚的地方可以从题目信息中推断

# 八、输出要求

你必须只输出一个严格合法的 JSON 对象，示例如下：

{
  "total_score": 95,
  "raw_score": 95,
  "positive_points_total": 100,
  "negative_points_total": -20,
  "matched_positive_points": 95,
  "matched_negative_points": 0,
  "rubrics_result": [
    {
      "criterion": "准确指出根因是 redis 容器未运行、停止或退出，导致投票链路中断",
      "points": 20,
      "matched": true,
      "reason": "选手明确指出 redis 容器未运行是导致投票链路中断的根因，符合题目要求。"
    },
    {
      "criterion": "正确定位故障组件为 redis，而不是 vote、worker、result 或 db",
      "points": 10,
      "matched": true,
      "reason": "选手将故障位置定位到 redis 服务，并说明 redis 位于 vote 和 worker 之间的队列环节。"
    },
    {
      "criterion": "使用 docker ps 或 docker compose ps 发现 redis 容器未处于运行状态",
      "points": 10,
      "matched": true,
      "reason": "选手通过容器状态检查发现 redis 未运行，证据方向正确。"
    },
    {
      "criterion": "补充 docker ps -a 或 docker compose ps -a，确认 redis 是否处于 Exited 状态",
      "points": 5,
      "matched": false,
      "reason": "选手使用 docker ps 检查容器状态，但未补充 docker ps -a 或 docker compose ps -a 来确认 redis 是否处于 Exited 状态，缺少更直接的退出状态证据。"
    },
    {
      "criterion": "引用 worker 日志中连接 redis 失败、Waiting for redis 或类似信息作为关键证据",
      "points": 10,
      "matched": true,
      "reason": "选手使用 worker 日志证明 worker 无法连接 redis，证据能够支撑诊断结论。"
    },
    {
      "criterion": "说明 vote 服务无法将投票数据写入 redis 队列",
      "points": 8,
      "matched": true,
      "reason": "选手说明 redis 停止后 vote 无法将投票请求写入队列，覆盖了上游影响。"
    },
    {
      "criterion": "说明 worker 无法从 redis 消费投票数据，导致数据库和 result 页面不更新",
      "points": 10,
      "matched": true,
      "reason": "选手说明 worker 无法消费 redis 队列，进而导致 db 和 result 页面不更新，因果链基本完整。"
    },
    {
      "criterion": "给出可执行的验证方法，例如重新提交投票并检查 result 页面是否更新",
      "points": 7,
      "matched": true,
      "reason": "选手提出了业务级验证方法，能够验证修复后投票链路是否恢复。"
    },
    {
      "criterion": "给出具体修复建议，例如启动 redis、执行 docker compose up -d redis 或重启相关服务",
      "points": 10,
      "matched": true,
      "reason": "选手给出了具体、可执行的 redis 恢复方案。"
    },
    {
      "criterion": "提出稳定性改进建议，例如 restart policy、healthcheck、监控告警或自动拉起机制",
      "points": 10,
      "matched": true,
      "reason": "选手补充了防止 redis 再次异常退出后长期不可用的稳定性改进建议。"
    },
    {
      "criterion": "错误地把根因判断为 Postgres 数据库故障",
      "points": -8,
      "matched": false,
      "reason": "选手没有将 Postgres 数据库作为主要根因，因此不触发该扣分项。"
    },
    {
      "criterion": "错误地把根因判断为 result 页面前端缓存或 result 服务自身异常",
      "points": -6,
      "matched": false,
      "reason": "选手没有将问题误判为前端缓存或 result 服务自身异常，因此不触发该扣分项。"
    },
    {
      "criterion": "提出危险或破坏性修复操作，例如无证据重装系统、删除数据库或替换系统盘",
      "points": -6,
      "matched": false,
      "reason": "选手没有提出危险或破坏性修复操作，因此不触发该扣分项。"
    }
  ],
  "issues": [
    "缺少 redis 容器 Exited 状态的直接证据。",
    "证据链可以进一步补充 docker ps -a 或 docker compose ps -a 的输出。",
    "业务级验证可以更完整，例如修复后重新提交投票并检查 result 页面是否更新。"
  ],
  "analysis_summary": "选手整体诊断正确，能够定位到 redis 容器未运行这一根因，并用 worker 日志和容器状态支撑结论。因果链基本完整，修复建议可执行，也包含一定的稳定性改进建议，因此整体给高分。主要不足是没有补充 redis 容器 Exited 状态的直接证据。",
  "improvement_suggestions": [
    "补充 docker ps -a 或 docker compose ps -a，确认 redis 是否处于 Exited 状态。",
    "补充修复后的业务级验证，例如重新提交投票并检查 result 页面是否更新。",
    "在证据部分区分直接证据和辅助证据，例如容器状态是直接证据，页面不更新是业务现象。"
  ]
}

注意：
最终只能输出 JSON，不要输出 Markdown，不要输出代码块，不要输出任何额外解释。
""".strip()


def _script_text(case, key):
    path = resolve_case_script(case, key)
    return path.read_text(encoding="utf-8") if path else ""


def build_grade_messages(case, answer_output, answer_transcript):
    case_json = {key: value for key, value in case.items() if not key.startswith("_") and key != "name"}
    process = answer_process_for_api_grading(answer_transcript, answer_output)
    user_prompt = GRADING_USER_PROMPT_TEMPLATE
    replacements = {
        "{{case.json}}": json.dumps(case_json, ensure_ascii=False, indent=2),
        "{{inject.sh}}": _script_text(case, "inject_script"),
        "{{recover.sh}}": _script_text(case, "recover_script"),
        "{{ideal-answer.json}}": json.dumps(case.get("_ideal_answer", {}), ensure_ascii=False, indent=2),
        "{{rubrics.json}}": json.dumps(case.get("_rubrics", {}), ensure_ascii=False, indent=2),
        "{{CONTESTANT_OUTPUT}}": answer_output or "（无最终诊断输出）",
        "{{CONTESTANT_PROCESS}}": process or "（无过程记录）",
    }
    for marker, value in replacements.items():
        user_prompt = user_prompt.replace(marker, value)
    return [
        {"role": "system", "content": GRADING_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
