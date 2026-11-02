# MCP tool boundary

Install from `agent-service` with `python -m pip install -e ".[dev]"`. The
project uses `mcp>=1.30,<2` with stdio transport. Start the Agent API with
`python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.

The Agent starts a separate Python MCP Server subprocess for each discovery or
call. The default command is its own Python interpreter running
`python -m app.mcp_server`. Set `MCP_SERVER_COMMAND` to a different Python
interpreter path if the API and Server use separate environments; set
`MCP_SERVER_MODULE` only for testing or deployment packaging. To launch the
Server independently for an MCP stdio host, set trusted environment variables
`HOUSE_MCP_SOURCE=mysql` and `HOUSE_MCP_TABLES=v_agent_house_listing`, then run
`python -m app.mcp_server`. The process communicates MCP JSON-RPC over stdin
and stdout; stdout must not be used for logging.

PowerShell example from `agent-service`:

```powershell
$env:HOUSE_MCP_SOURCE = 'mysql'
$env:HOUSE_MCP_TABLES = 'v_agent_house_listing'
.\.venv\Scripts\python.exe -m app.mcp_server
```

An MCP stdio client must attach to that process's stdin and stdout. For the
Agent API, set the usual database and model values in `.env`; it starts the
scoped Server itself and does not require a separately managed listening port.

The trusted Jev and routing policy select a data source and views before the
Agent starts the Server. The Agent passes that scope, row limit, enablement,
and connection configuration through the subprocess environment. None of these
fields appear in model tool arguments. `tools/list` exposes the metric tool and
only the selected source's schema and query tools. `tools/call` is handled by
the Server's turn-scoped registry using the existing Pydantic contracts,
SQLGlot read-only validation, whitelist, row limit and database adapters.
The MySQL adapter closes each connection after a query and the Server disposes
its engine on exit; Hive closes each connection after use.

The Agent still binds the discovered schemas to the model for structured
Function Calling. It executes every accepted tool call through MCP, applies
model/tool/successful-query limits, and maps MCP failures to existing tool
errors. A stopped or broken Server returns HTTP 503 from the chat API.
`query_result` and the tool transcript remain `UntrackedValue` in LangGraph,
so query rows are not written into checkpoints. This change does not add ReAct,
housing-platform connectivity, or policy RAG.

For a protocol test without MySQL or Hive, run
`python -m pytest -q tests/test_mcp_integration.py`. It starts a real MCP
subprocess with test database adapters, exercises `tools/list` and
`tools/call`, and sends normal requests through `/api/v1/chat`. Live database
and model smoke tests require the corresponding credentials and services.
