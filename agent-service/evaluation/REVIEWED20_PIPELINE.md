# 审核版 20 题评测流水线

## 现有实现与口径

- `structural-2026-10-23/run_new20.py` 已按题独立调用 `/api/v1/chat`，记录请求、完整响应和耗时；三道多轮题将上一问返回的 `thread_id` 传入末轮。本流水线沿用同一请求格式。
- `real-baseline/score_live.py`、`structural-2026-10-23/score_exposed.py`、`real-regression-2026-10-23/score_regression.py` 已有 HTTP、Jev 标签、最终数据源、SQL 行、政策证据和答案词项的分项检查。本流水线沿用这些分项名称和历史基线含义，但不把它们折算为整题通过。旧脚本的数值容差、证据代理命中和文字包含判断不能独立证明用户任务完成。
- `app/evaluation/jev_routing.py` 与 `jev_review.py` 是单独的 Jev 路由评测；后者需要模型调用。本流水线只读取真实响应中已有的 `route_suggestion`，离线评分时不调用 Jev/LLM。
- 2026-10-30 综合报告对审核版 20 题的人工判读为 11 通过、4 部分通过、5 未通过。这是历史人工结论，不自动移植为新运行的成绩。

## 标准审查

审核版 CSV 有 20 个唯一 ID，`should_answer` 为 17 个 `true`、3 个 `false`；`expected_intent`、`expected_source`、`must_include`、`must_not_include` 与 `acceptable_range` 都有值。`acceptable_version_ids` 在 8 个纯数据题为空，`sql_verification` 在 10 个纯政策题为空。它们是条件性字段。`rag_retrieval` 在部分纯数据题为自然语言“无”，不是 JSON，不应按 JSON 字段处理。

- **BLD16**：技术溯源确认源 CSV 的 `unit_price` 均值为 `83067.26`，Java 导入器按 `total_price*10000/area` 逐条四舍五入后写入 MySQL，视图均值为 `83067.230324675`。本题明确查询 MySQL，故标准改为 `83067.23`；原 CSV 保留，流水线不再标为 `oracle_pending`。
- **BLD07/08**：经北京市政府官网文号、正文、有效性标记核对，并经用户确认以官网 HTML 为审核依据，360/565 正式证据准入。`official_html_approved` 仅赋给这两份来源，重新规范化和入库后不再标为 `oracle_pending`；后续条款覆盖仍须按问题逐条判断。
- **BLD12**：标准 SQL 同时投影样本数和均值，历史在线 SQL 仅投影均值；若均值匹配，标记 `projection_review`，保留人工核查。

## 使用

从仓库根目录运行，PowerShell：

```powershell
$env:PYTHONPATH = 'agent-service'
python -m app.evaluation.reviewed20 validate
python -m app.evaluation.reviewed20 score --raw agent-service/evaluation/real-regression-2026-10-23/new20_reviewed_2026-10-30.jsonl
python -m app.evaluation.reviewed20 all --endpoint http://127.0.0.1:8000/api/v1/chat
python -m app.evaluation.reviewed20 compare --old <旧输出目录> --new <新输出目录> --output <新比较文件.json>
python -m app.evaluation.reviewed20 report --output <已有输出目录>
```

`all` 是“校验 → 请求 → 保存完整响应 → 客观评分 → 报告”的单命令。`run` 只保存响应，`score --raw` 可离线回放。默认输出至 `agent-service/evaluation/runs/<UTC 时间戳>-<题集 hash 前缀>/`，已有目录会拒绝覆盖。输出包括 `metadata.json`、`raw.jsonl`、`scored.jsonl`、`cases.csv`、`summary.json`、`report.md`。题集原文件及旧结果均不写入。

人工判定使用单独 JSONL，例如：

```json
{"case_id":"BLD01","decision":"pass","reason":"人工核对回答符合边界与事实","reviewer":"姓名或工号","reviewed_at":"2026-11-01T12:00:00+08:00"}
```

用 `score --raw <原始响应> --adjudications <判定.jsonl>` 生成新的输出目录。`decision` 只接受 `pass`、`partial`、`fail`。不要修改题集 CSV。

数值按标准的**分**位精度四舍五入比较，额外容差为零；`[[0]]` 与 `[]`、缺失 `rows` 分别记录。SQL 比较城市、地区、房源类型、必要排序和条数；BLD13 的地区 `IN` 条件及 BLD15 会排除零行的过滤也单独检查。SQL 文本无需逐字相同。答案词项仅报告缺失或禁止词命中，语义事实仍需人工判读。政策文号、版本、条款、出处分别给证据，不因存在政策片段便判整题通过。P50/P95 是串行运行的单题耗时，不是并发压测。

## CI

`.github/workflows/agent-evaluation.yml` 的普通提交和 PR 只运行题集校验、13 个确定性 pytest 和固定历史响应 replay，上传报告构建产物，不调用外部服务。手动 `workflow_dispatch` 勾选 `live_20` 后才会运行真实 20 题。仓库变量 `AGENT_EVAL_ENDPOINT` 必须指向 runner **可访问**的 `/api/v1/chat`；GitHub 托管 runner 的 `127.0.0.1` 指向 runner 自己，不能访问开发机服务。可选公开变量 `OPENAI_MODEL`、`JEV_MODEL` 只用于报告版本信息。服务侧的 OpenAI、Jev、MySQL、Hive、Qdrant 等密钥和依赖由受控服务环境配置，流水线不会从 GitHub 假定它们已存在，也不会在报告记录密钥。真实评测的波动只作为报告和比较产物，不阻断普通 PR。
