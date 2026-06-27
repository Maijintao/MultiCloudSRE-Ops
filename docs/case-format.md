# Case Format

Each case lives in `faults/<case-id>/`.

```text
case.json
ideal-answer.json
rubrics.json
inject.sh
recover.sh
```

Only `case.json` is public contestant-facing material. The other files are
server-side evaluation and operations material.

## `case.json`

Required fields:

- `id`: stable case id, matching the directory name.
- `title`: short display title.
- `fault_phenomenon`: user-visible symptoms.
- `public_case_info`: public environment and tool guidance.
- `order_id`: display order.

Optional fields:

- `inject_script`: path to a script run before the answer attempt.
- `recover_script`: path to a script run after the answer attempt.
- `submission_enabled`: whether contestants can submit this case directly.
- `ai_analysis_visible`: whether contestants can inspect AI analysis output.
- `case_set_id`: `training`, `ungrouped`, or a configured test-set id.
- `mcp_servers`: private runtime MCP selection, not exposed to contestants.

## Private Scoring Files

`ideal-answer.json` describes the expected diagnosis. `rubrics.json` contains
positive and negative scoring points for the grader. For real competitions,
keep both files private.

## Scripts

`inject.sh` and `recover.sh` run on the OJ host. The bundled demo scripts use
`faults/lib.sh`, which executes commands locally under `VOTING_APP_DIR` or over
SSH when `FAULT_TARGET_HOST` is configured.

Scripts should be idempotent, bounded by timeouts, and careful with destructive
operations.
