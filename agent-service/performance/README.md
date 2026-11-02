# 后端性能与 Jev 稳定性测试

仅请求 Python Agent 的 `/health` 和 `/api/v1/chat`。先安装：

```powershell
cd agent-service
.\.venv\Scripts\python.exe -m pip install -e '.[performance]'
```

完整命令（默认全负载 1/5/10 用户；每档从目标用户全部启动后预热 10 秒、采样 120 秒；估算 25 美元总上限）：

```powershell
.\.venv\Scripts\python.exe performance\run.py
```

包含 Hive 的较长正式运行（每档采样 180 秒；最多按每个聊天请求 0.02 美元估算 30 美元，不代表实际账单）：

```powershell
.\.venv\Scripts\python.exe performance\run.py --workloads health sql_mysql rag mixed sql_hive --users 1 5 10 --warmup 10 --sample 180 --spawn-rate 10 --timeout 60 --max-requests 10000 --max-requests-per-cell 300 --max-health-requests-per-cell 3000 --max-external-calls 13500 --budget-usd 30 --estimated-usd-per-chat 0.02
```

指定负载和档位，例如只验证 10 用户：

```powershell
.\.venv\Scripts\python.exe performance\run.py --workloads sql_mysql rag --users 10 --warmup 10 --sample 180 --spawn-rate 10 --max-requests 3000 --max-requests-per-cell 300 --max-external-calls 5400 --budget-usd 12
```

每次在 `performance-results/<UTC时间戳>/` 新建目录，绝不覆盖旧结果。参数还包括 `--base-url`、`--max-health-requests-per-cell`、`--timeout`、`--seed`、`--estimated-usd-per-chat`、`--output-root`、`--jev-kind`。`--max-requests` 是所有档位共用上限；`--max-requests-per-cell` 是每个聊天档位上限。额度不足以启动目标用户数时，该档明确标记未测。预算按请求估值限制次数，**不是供应商账单**；正式大样本前应使用实际模型定价和 token 数据重新估算。低于 100 个正式样本的 P95 仅供观察。`sql_hive` 需显式加到 `--workloads`，Hive 未启用时单列未测。

虚拟用户可以并行，每人一次只发一条请求。`--spawn-rate 10` 会较快启动 10 人，但请求极快的 `/health` 即使 10 人均已启动，实际同时在途数仍可能低于 10；这不等于服务只能接待这么多人。报告同时记录目标用户、实际启动用户及实际在途峰值。正常问答和短时突发是不同负载模型，本脚本测的是持续用户负载。采样期是否完整也会写入报告。

`workloads.json` 固定审核题和最小机器断言。运行前的真实预检逐题核对响应源、业务字段和依赖；失败时该负载所有档位停止。每个聊天请求不传 `thread_id`，由 Agent 建立新会话。原始 JSONL 仅保留 trace_id、类别、数据源、调用数、token 和分段耗时，不保存完整问答或密钥。Locust CSV 与进程日志保存在同目录。

本地 Jev 故障演练会暂时重建**本项目** `python-agent` 容器，指向主机上的测试 stub，结束时在 `finally` 里按原环境重建并检查 `/health`：

```powershell
.\.venv\Scripts\python.exe performance\fault_drill.py --stage-seconds 15 --max-requests 40
```

故障报告目录带 `jev-stub-fault` 后缀，与真实 Jev 结果隔离。stub 只代替 Jev 路由返回当前 Choice/Noul 契约；SQL、LLM、MCP 仍走 Agent 原链路。超时延迟超过 `--jev-timeout`；断连关闭连接；阶段之间不重启 Agent。控制接口只接受本机回环地址。运行前确保 8765 端口未占用、Docker Compose 可用，并确认当前 Agent 容器可短时重建。故障演练产生真实 LLM 调用，应设置请求上限。

`details.route_duration_ms` 包含 Jev 和可能的复核；`jev_duration_ms` 是单独的 Jev 调用。Qdrant 字段只计 `query_points`；本地重排另计；SQL 字段只计实际执行，不含 MCP 启动。服务端总耗时优先取 `X-Server-Duration-Ms`，覆盖 API 请求与审计写入；旧 `details.duration_ms` 结束于审计写入之前。各段重叠，不能求和。未经过的阶段和未采集的阶段必须保持空值。
