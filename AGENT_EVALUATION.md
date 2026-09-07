# Agent 自动化评测

评测程序位于 `agent-service/app/evaluation/`，通过 HTTP 调用 Agent，不依赖前端。当前数据集为 schema `2.0`，包含原有 10 个分组的 80 个单轮用例，以及“连续对话”分组的 8 个多轮用例，共 88 个 case。每个 case 都绑定 `SYNTHETIC_CSV_V1_5000` 和 CSV SHA-256：`678a7f143383198b1ea035e9c3265636c4f770290b5c32beef1f6bf6b9935979`。

## 运行

```powershell
cd agent-service
.\.venv\Scripts\python.exe -m app.evaluation --dataset ..\agent-evaluation-dataset.jsonl --base-url http://localhost:8000/api/v1/chat --output-dir ..\evaluation-results --max-cases 3
```

安装项目后也可用 `house-agent-eval`。CLI 支持 `--run-id`、`--baseline`、`--groups`、`--case-ids`、`--timeout`、`--concurrency`、`--pricing-file`、`--fail-on-regression` 和 `--max-cases`。默认并发为 1；不同 case 可并发，但同一多轮 case 始终顺序执行并复用自己的 `thread_id`。完整 88 case 会调用模型并产生费用，必须明确决定后再运行。

退出码：`0` 全部通过，`1` 有失败或要求检查的回归，`2` 参数、数据集、快照或健康预检失败。

## 快照与断言

当前 CSV 是 5000 行活动快照，SALE/RENT 各 2500 行。旧版基于 20 行样例的自然语言 `facts` 已移除。数据集现在使用 `turns[].expected.assertions`，支持精确行数、必需列、指定单元格数值和容差、SQL 必含/禁含内容及答案必含事实。`upgrade_dataset.py` 从 CSV 读取数量并生成快照绑定字段，禁止凭记忆填写固定数量。

## 输出与回归

每次运行创建 `evaluation-results/<run-id>/`：`raw-results.jsonl`、`scored-results.jsonl`、`summary.json` 和 `report.md`。`--baseline previous/scored-results.jsonl --fail-on-regression` 会把原先通过、当前失败的同一 case/turn 标为回归。评分完全确定性，不调用第二个 LLM。

## Token 与费用

Agent 在统一模型调用封装中累计 SQL 生成、SQL 修复和答案生成的调用次数及 Token，返回于 `details` 并写入 `agent_query_audit`。确定性拒绝为 0 次；供应商不提供 usage 时 Token 为 `null`。费用仅由 Runner 读取 JSON 价格：`{"input_usd_per_million": 0.4, "output_usd_per_million": 1.6}`。未配置价格时费用为 `null`，绝不当作 0 美元。

Runner 只向 `/api/v1/chat` 发送自然语言，不直接执行数据集中的 SQL，不读取或输出 API Key、数据库密码或完整环境变量。
