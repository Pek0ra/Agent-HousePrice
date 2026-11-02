"""Synchronous turn client backed by an actual MCP stdio subprocess."""

from __future__ import annotations

import os
import sys
from typing import Any

import anyio
from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import Settings
from app.tools.contracts import ToolError, ToolResult


class McpUnavailableError(RuntimeError):
    pass


class TurnMcpClient:
    def __init__(self, settings: Settings, source: str, selected_tables: set[str]) -> None:
        self._settings = settings
        self._source = source
        self._tables = selected_tables

    def _parameters(self) -> StdioServerParameters:
        env = {**os.environ,
            "HOUSE_MCP_SOURCE": self._source,
            "HOUSE_MCP_TABLES": ",".join(sorted(self._tables)),
            "BIG_DATA_ENABLED": str(self._settings.big_data_enabled).lower(),
            "SQL_MAX_ROWS": str(self._settings.sql_max_rows),
            "SQL_EXECUTION_TIMEOUT_MS": str(self._settings.sql_execution_timeout_ms),
            "MYSQL_HOST": self._settings.mysql_host,
            "MYSQL_PORT": str(self._settings.mysql_port),
            "MYSQL_DATABASE": self._settings.mysql_database,
            "MYSQL_USERNAME": self._settings.mysql_username,
            "MYSQL_PASSWORD": self._settings.mysql_password,
            "HIVE_HOST": self._settings.hive_host,
            "HIVE_PORT": str(self._settings.hive_port),
            "HIVE_DATABASE": self._settings.hive_database,
            "HIVE_USERNAME": self._settings.hive_username,
            "HIVE_AUTH": self._settings.hive_auth,
            "POLICY_QDRANT_LOCATION": self._settings.policy_qdrant_location,
        }
        command = self._settings.mcp_server_command or sys.executable
        return StdioServerParameters(command=command,
            args=["-m", self._settings.mcp_server_module], env=env,
            cwd=os.path.dirname(os.path.dirname(__file__)))

    async def _exchange(self, name: str | None, arguments: dict[str, Any] | None):
        async with stdio_client(self._parameters()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                page = await session.list_tools()
                tools = page.tools
                if name is None:
                    return tools
                if name not in {tool.name for tool in tools}:
                    return ToolResult(ok=False, error=ToolError(code="unavailable", message="本轮不可使用该工具。"))
                result = await session.call_tool(name, arguments=arguments or {})
                if result.isError or result.structuredContent is None:
                    return ToolResult(ok=False, error=ToolError(code="execution_failed", message="MCP 工具执行失败。"))
                return ToolResult.model_validate(result.structuredContent)

    def _run(self, name: str | None, arguments: dict[str, Any] | None = None):
        try:
            return anyio.run(self._exchange, name, arguments)
        except Exception as exc:
            raise McpUnavailableError("MCP Server 不可用，请检查独立工具进程及配置。") from exc

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(tool.name for tool in self._run(None))

    def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        return self._run(name, arguments)

    def as_langchain_tools(self) -> list[Any]:
        tools = self._run(None)
        return [StructuredTool.from_function(
            func=lambda _name=tool.name, **kwargs: self.invoke(_name, kwargs).model_dump_json(),
            name=tool.name, description=tool.description or tool.name,
            args_schema=tool.inputSchema,
        ) for tool in tools]
