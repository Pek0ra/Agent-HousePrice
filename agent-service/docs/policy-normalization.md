# 政策文件离线规范化

此入口仅用于政策入库和更新。在线问答代码不导入它，也不运行 PDF、MHTML 解析或 OCR。

## 运行

在 `agent-service` 目录执行：

```powershell
python -m pip install -r requirements-policy.txt
python -m app.rag.policy_normalize
```

默认读取 `../data/RAG` 顶层的原文件，输出到 `../data/RAG/normalized`。首次运行会按 `app/rag/policy_sources.json` 中的官网地址保存 HTML 快照到 `../data/RAG/official_html`。之后可断网重复运行；只有原文件哈希或来源配置改变才重建对应 Markdown。政策官网正文更新时，运行 `python -m app.rag.policy_normalize --refresh-official`，取得并验证新快照后重建。原文件不会被修改。

`normalized/manifest.json` 是后续程序的输入清单。仅处理 `status` 为 `machine_checked` 且人工准入完成的记录；`needs_manual_review` 在逐页核对前不要进入正式索引；`failed` 必须停止入库。读取清单中的 `markdown_path`，不要直接枚举目录。每份 Markdown 的 front matter 包含 `version_id`、`source_url`、`original_path`、`original_sha256`、`title`、`document_number`、`issuing_authority`、`publication_date`、`effective_date`、`retrieved_at`、`parse_method` 和 `verification_status`。空值为 `null`。`normalized/reports/quality_report.md` 列出缺失字段、关键表达抽样和待核对项。

切块时以 `## 一、` 等一级条款为主边界，继续按 `### （一）`、`#### 1.` 分割过长条款；把上级标题、原条款编号、`version_id`、文号、日期和原文件哈希附在每块，引用时显示完整层级。保留条款中的例外条件、数字与日期，不按固定字数截断一句条款。具有相似标题的新版和旧版各自保留；此目录不判断旧条款现今是否有效。

## 文字来源与核查

PDF 首先抽取文本层并检查中文占比和乱码。四份网页打印 PDF 的正文行或页脚与正文交错，使用对应政府官网 HTML 快照提供完整正文；两份公报 PDF 的文本层不可读，依据可见文号取同文号官网 HTML。原 PDF 保留作凭证。HTML 下载失败且本地无快照时，公报才尝试本机中文 OCR；OCR 不可用或输出未过质量门槛就失败，不生成 Markdown。两份公报的哈希被固定在来源配置中；原件变化需重新目视核查并更新哈希。MHTML 从 MIME 的 HTML 部分抽取 `.arc_cont`，不当成 Word 解析。

抽样对照如下。左列来自原件的可见页面或 MHTML 正文；右列是 Markdown 的对应表达。此对照只核查文字处理，不确认政策时效性。

| 原件 | 原文抽样 | Markdown 核查 |
| --- | --- | --- |
| 2025 利率网页打印 PDF | PDF 正文显示首套 2.1%、2.6%，二套 2.525%、3.075%；右边界截断 | 四个利率和 2026 年 1 月 1 日均在官网正文快照及 Markdown 中 |
| 2024 年 218 号网页打印 PDF | “二孩及以上”“首套住房认定标准”；浏览器页脚夹杂 | 条款一至四、落款和 2024 年 6 月 26 日保留，页脚剔除 |
| 公报 PDF，京建发〔2025〕360号 | 首页可见文号和“一、进一步优化住房限购政策” | 同文号官网正文含 100 万元、30%、15 万元，全文待逐页人工核对 |
| 公报 PDF，京建发〔2025〕565号 | 首页可见文号；其同名文件容易与 2024 年 400 号混淆 | 同文号官网正文含 2 年、1 年、25%，全文待逐页人工核对 |
| 2024 年第 16 号 MHTML | MIME HTML 正文含唯一住房 140 平方米、1% 和 1.5% | 层级“一、”“（一）”及比例、2024 年 12 月 1 日保留 |
| 2026 年第 3 号 MHTML | MIME HTML 正文含 2026 年 1 月 1 日至 2027 年 12 月 31 日、1 年内换购 | 两个日期、退税条件及“同一城市范围”保留 |

2026-11-01 更新：360/565 号已核对北京市政府官网页面的文号、正文关键数字、施行条款及“有效”标记；用户确认以官网 HTML 为正式引用审核依据，来源配置标记为 `official_html_approved`。本地 PDF 文本层仍不可读，未做逐页版式对照。准入只确认可引用来源，不表示每一旧条款均未被后续政策调整；回答仍须逐条判断日期与适用范围。
