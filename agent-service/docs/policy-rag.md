# 北京购房政策 RAG

## 运行

在 `agent-service` 目录安装依赖：`python -m pip install -e '.[dev]'`。本地 Qdrant 模式默认写入 `data/policy_qdrant`；部署时 `docker compose up -d qdrant python-agent`，`python-agent` 使用 `POLICY_QDRANT_LOCATION=http://qdrant:6333` 和只读挂载的 `/data/RAG/normalized`。容器中执行 `docker compose exec python-agent python -m app.rag.policy_cli build`。

本地命令：

```powershell
cd agent-service
python -m app.rag.policy_cli validate
python -m app.rag.policy_cli build
python -m app.rag.policy_cli update
python -m app.rag.policy_cli inspect
python -m app.rag.policy_cli search '京建发〔2026〕400号公积金240万元'
python -m app.rag.policy_cli search '2024年10月1日五环内社保年限' --as-of 2024-10-01
python -m app.rag.policy_eval
python -m pytest -q
```

`build` 与 `update` 使用相同的增量操作。`validate` 只读入 Markdown、manifest 和来源目录；问题请求不读取 PDF、DOC 或 HTML。仅在入库时计算 embedding。索引与原业务指标 Markdown 检索器独立。稠密模型为 `BAAI/bge-small-zh-v1.5`，索引记录 fastembed 包版本；中文双字组作稀疏召回，文号与数字作精确加权，融合后重排。Qdrant Server 上会建立审核、城市、主题和生效日期字段索引；本地 Qdrant 模式没有 payload 索引加速。

## 入库状态与审核

2026-10-22 本地构建结果：

| 文件 | 状态 | 块数 | 正式答案 |
| --- | --- | ---: | --- |
| bj-gjj-rate-2025-05-08.md | machine_checked，生效日 unknown | 3 | 可引用原文，时效需核对 |
| bj-housing-2024-218.md | machine_checked | 5 | 可引用，现行效力仍需核对 |
| bj-housing-2024-400-web.md | machine_checked | 9 | 可引用，后续条款覆盖需核对 |
| bj-housing-2025-360.md | needs_manual_review | 9 | 排除，待人工逐条核对 |
| bj-housing-2025-565-bulletin.md | needs_manual_review | 6 | 排除，待人工逐条核对 |
| bj-housing-2026-400.md | machine_checked，推导 2026-08-08 | 12 | 可引用，生效推导待核对 |
| tax-2024-16.md | machine_checked | 10 | 可引用 |
| tax-2026-3.md | machine_checked | 8 | 可引用 |

共 62 块。2026 年第 400 号的日期由发布日期加一日推导，依据原句“本通知自印发次日起施行”，标记 `derived_unverified`。利率公告的 `effective_date` 仍为 null；正文对不同贷款发放时间的具体执行日期保留在原文中。所有 `effective_to` 在缺少已核实条款级覆盖关系前留空，不能据此断言当前有效。

人工审核应对照两份公报 PDF 的可见版式、落款、文号、关键数字和官方网页原文，再核对生效时间、废止和条款覆盖关系。审核结果须由人工修改 Markdown front matter 和 manifest 中对应状态，并记录审核人、日期、证据；程序不会自行修改这两份文件的状态。尤其第 565 号曾与第 400 号混淆，需核对公报首页。来源、文号、URL 与 `policy_sources.json` 校验一致。

## Agent 调用

Jev 的 `policy`/`policy_listing` 意图进入权限路由。`policy` 只启动政策 MCP 进程，暴露 `search_policy`/`read_policy_clause`；该权限没有 SQL 视图。组合请求另启受控 SQL MCP：普通项目样本使用 MySQL `v_agent_house_listing`；明确指定当前 CSV 导入数据且 Hive 可用时使用 Hive `v_agent_house_info_analysis`。两条路径均沿用只读 SQL 白名单验证，再与政策证据合并。项目 CSV 为合成样本，回答明确标注，不能称作真实市场挂牌。政策回答给出条款原文、文号、条款路径、官方 URL、未知用户条件及时间和版本限制。指定未审核文号时拒绝拿其他文号代答。MCP 或 Qdrant 故障时政策结论降级为证据不可用；SQL MCP 故障返回服务不可用。

## 2026-10-22 检索优化评测

人工核对的 12 题位于 `tests/data/policy_questions.jsonl`，10 题有答案，2 题应拒答。当前仅比较同一索引上的纯稠密召回与混合检索重排；未训练 embedding 或 reranker。

| 策略 | Recall@1 | Recall@5 | 首条引用正确率 | 无答案拒答 |
| --- | ---: | ---: | ---: | ---: |
| 稠密基线 | 0.80 | 0.90 | 0.80 | 0.00 |
| 混合检索及重排 | 1.00 | 1.00 | 1.00 | 1.00 |

基线失败例：问“京建发〔2024〕218号哪天施行”未在前五条找到该文件；指定未审核的第 565 号却返回别的文件；“外星人特殊优惠”也返回了不相关条款。优化后在这 12 题没有 Recall@5、首条引用或拒答失败；这个小题集不能证明真实场景的政策效力判断。带日期题的未来版本误用计数为 0；条款级废止/覆盖尚未人工核实，不能把这项计作完整的过期条款误用率。

模型微调尚未开始。题集太小，缺少经过人工核对的正例与困难负例和独立测试集；当前工作属于切块、过滤、权重及重排的检索优化。
