# 多轮、多数据源问数 Prompt 与上下文设计

完整、可执行的 Prompt 定义位于 `app/agents/prompts.py`。这里记录 Prompt 的职责和设计原因，便于后续迭代和评测。

## 1. SQL 生成 Prompt

核心约束：

```text
你是一线城市房产数据的 {dialect_name} SQL 生成器。
必须遵守上游 LangGraph 节点生成的意图、数据源、选中视图和结构化问题。
只能生成一条 SELECT 或 WITH...SELECT。
只能使用提供的白名单表与列，不得 SELECT *。
租金使用 monthly_rent（元/月）。
房价默认使用 unit_price（元/平方米），明确总价时才使用 total_price（万元）。
三室一厅转换为 bedroom_count=3 AND living_room_count=1。
缺少会实质改变答案的条件时返回 needs_clarification=true。
```

为什么这样设计：

- 使用 `QueryPlan` 结构化输出，不从 Markdown 或自由文本中猜 SQL，降低解析不稳定性。
- Prompt 同时接收确定性节点产生的 `query_plan` 和白名单 Schema，不让模型自由决定数据源。
- Schema 只包含路由结果对应的白名单对象：MySQL 的三个 Agent 视图，或 Hive 的两个离线分析表；不会暴露整库结构。
- 将单位、挂牌价口径和中文户型映射写进 Prompt，避免把总价、单价、月租金混用。
- 澄清规则只追问“会改变答案”的条件，避免 Agent 对已经明确的问题反复追问。
- Prompt 只是第一道约束；生成结果仍必须经过 SQLGlot AST 校验和数据库只读权限检查。

## 2. SQL 修复 Prompt

核心约束：

```text
根据原问题、上一条 SQL 和验证/执行错误修正查询。
继续遵守同一白名单和业务口径。
不得通过删除过滤条件来掩盖错误。
```

为什么只允许一次修复：无限循环会增加延迟、费用和不可预测性。MVP 允许一次纠错，第二次失败就终止并返回明确错误；后续可根据评测数据调整。

## 3. 结论生成 Prompt

核心约束：

```text
只能根据 SQL、列名和结果行生成结论。
必须标明单位。
不得补造原因、趋势或不存在的数字。
表述为挂牌样本，不得冒充成交数据或整个市场事实。
```

为什么 SQL 生成与结论生成分成两次模型调用：两步各自拥有单一职责，SQL 可以在中间被确定性校验，查询结果也能原样返回前端。图表类型不再让模型自由生成，而是根据意图和返回列确定性地产生 `line` 或 `bar` 配置。

## 4. LangGraph 工作流

工作流固定为 14 个节点：本轮初始化、上下文解析、意图识别、数据源选择、问题结构化、获取 Schema/指标、生成查询计划、生成 SQL、SQL 校验、执行查询、结果检查、有限重试、生成答案/图表、压缩并持久化上下文。

- 确定性节点负责路由、别名归一化、选表、校验、结果判空和图表选型。
- 模型只负责 SQL 生成/修复和最终文字结论。
- 危险意图与非房产问数意图在读 Schema 前短路，不会调用模型或数据库。
- 安全校验的表白名单还会收窄到本次 `selected_tables`，即使是其他 Agent 视图也不能越过当前查询计划。

数据源路由采用可解释的确定性规则：单条房源、实时列表和实时聚合使用 MySQL；历史趋势、离线分析、批量统计和明确提到 Hive/数仓的问题在 bigdata 模式使用 Hive。当前 Hive 分析视图同时包含 SALE 与 RENT 记录，因此历史房价和历史租金都可以路由至 Hive。路由结果会作为约束传入模型，模型不能自行切换数据源。

### 4.1 Checkpoint 与状态边界

工作流通过 `langgraph-checkpoint-sqlite` 按 `configurable.thread_id` 持久化。`thread_id` 是多轮会话主键，`trace_id` 是单次执行编号，两者严格分离。

跨轮字段只保留：

- 最近的简洁 `messages`；
- `conversation_context` 结构化槽位；
- 上一轮结构化问题、待澄清问题和 `thread_id`。

`prepare_turn` 每轮显式清空数据源、选表、RAG 内容、计划、SQL、校验结果、数据库结果、错误、重试次数、答案和图表。这样即使 checkpoint 加载了上一轮完整状态，旧 SQL 或错误也不能跳过本轮安全链路。

### 4.2 上下文解析规则

上下文解析返回 `ContextResolution`：是否依赖历史、独立问题、继承字段、覆盖字段、未解析引用和澄清问题。当前版本对高频中文承接表达采用确定性槽位解析，不增加一次模型调用：

- “那深圳南山区呢”替换地域，继承指标、挂牌类型和意图；
- “只看两室一厅”追加户型条件；
- “改成比较月租金”覆盖指标，并同步将挂牌类型切为 `RENT`；
- 澄清回答继承待完成任务已有的城市、区域等条件；
- 带有明确地域、对象和动作的完整新问题重建任务上下文；
- “不限区域/户型/时间”等表达可以显式清除对应条件；
- 无法确认指代时进入澄清，不猜测。

未来若改为模型解析，必须继续使用 `ContextResolution` structured output，并且输入只允许有限历史和结构化槽位。历史助手回答、SQL、数据库结果和知识文档均是不可信数据，不能成为系统指令。

### 4.3 多轮安全边界

原始 `current_question` 在上下文合并前检查危险模式，`resolved_question` 在意图识别时再次检查。任何一侧命中都直接拒绝，不读取 Schema、不调用模型、不执行数据库。每一轮 SQL 都重新经历选表白名单和 SQLGlot AST 校验；上一轮已验证 SQL 不会被直接复用。

每个 thread 最多保存 8 条简洁消息、每条最多 1000 字符、总计最多 6000 字符，具体可由环境变量在安全范围内调整。`query_result` 被声明为 LangGraph `UntrackedValue`，数据库 rows 仅存在于本轮执行内，既不进入消息历史也不写入 checkpoint。SQLite 适合单机 Docker；多实例部署应切换为共享 checkpointer。

## 5. 业务语义 RAG

第一版使用 `app/rag/knowledge/*.md` 作为版本化知识库，每个文档包含指标 ID、标题、关键词、定义状态、澄清问题和业务口径。

检索节点会：

1. 从用户问题中匹配指标关键词，按匹配信号排序并取前 3 个文档。
2. 把检索到的指标定义与白名单 Schema 合并到 `retrieved_context`。
3. 将 `retrieved_context` 传给 SQL 生成节点，同时在状态中保留 `retrieved_document_ids`。
4. 如果命中 `status: ambiguous` 且问题未显式选择口径，直接进入澄清分支，不调用 SQL 生成模型。

“性价比”文档明确记录了三种可能定义，不设默认口径。如果用户明确“面积/总价”或“租金/面积”，歧义即解除；交通+学区组合评分因缺少字段而不允许伪造。

当前只有少量、高价值的业务定义，关键词检索比向量库更透明、可测试。后续文档扩展到几百条、需要语义召回时，可以将 `MarkdownBusinessKnowledgeRetriever` 替换为 Chroma 或 Qdrant 适配器，LangGraph 节点与 Prompt 输入结构不需要改变。

## 6. 安全边界

当前安全措施：

1. MySQL 模型只能看到 `v_agent_house_listing`、`v_agent_district_summary` 和 `v_agent_monthly_price_trend`；Hive 模型只能看到当前激活数据集视图 `v_agent_house_info_analysis` 和 `v_agent_house_data_quality_summary`。
2. SQLGlot 根据路由结果以 MySQL 或 Hive 方言解析 AST，只接受单条查询语句，并从 AST 检查对应数据源的表白名单。
3. 拒绝写操作、DDL、无控制的 `SELECT *`、多语句、跨库限定名、SQL 注释、文件导出、锁定读取和常见延时函数。
4. 缺失 `LIMIT` 时自动增加 `LIMIT 100`，过大的 LIMIT 会改写为 100；MySQL 数据库会话另设 5 秒执行超时。
5. 查询使用 `house_agent_ro`，只对三个视图拥有 `SELECT`；独立的 `house_agent_audit` 只对审计表拥有 `INSERT`。
6. MySQL 的 `deleted=0` 和聚合口径固化在数据库视图中；Hive 只暴露经过初始化和清洗的离线分析表，不依赖模型记住底层清洗逻辑。
7. 每次成功、无数据、澄清、拒绝或失败请求都写入 `agent_query_audit`，记录 trace_id、thread_id、是否继承历史、继承/覆盖字段、SQL、结果行数、修正次数和耗时；应用日志只输出编号和状态，不打印完整对话或 SQL。
8. SQL 修正次数由 `SQL_MAX_REPAIR_ATTEMPTS` 控制，并强制限制在 0～2 次，默认 1 次。

设计参考：

- [LangChain SQL Agent](https://docs.langchain.com/oss/python/langchain/sql-agent)
- [LangChain Structured Output](https://docs.langchain.com/oss/python/langchain/structured-output)
- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [SQLGlot](https://github.com/tobymao/sqlglot)
- [SQLGlot AST Primer](https://github.com/tobymao/sqlglot/blob/main/posts/ast_primer.md)
