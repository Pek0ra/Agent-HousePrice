"""Turn-scoped MCP server. The trusted parent process supplies scope via environment."""

from __future__ import annotations

import os

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from app.config import Settings
from app.database.mysql import MysqlQueryDatabase
from app.tools.registry import build_tool_registry


def create_server(*, settings: Settings, source: str, selected_tables: set[str],
                  mysql_database=None, hive_database=None, retriever=None) -> Server:
    if source not in {"mysql", "hive", "policy"}:
        raise ValueError("Invalid MCP source")
    if source != "policy":
        mysql_database = mysql_database or MysqlQueryDatabase(settings)
    if source == "hive" and hive_database is None and settings.big_data_enabled:
        from app.database.hive import HiveQueryDatabase
        hive_database = HiveQueryDatabase(settings)
    registry = build_tool_registry(settings=settings, source=source,
        selected_tables=selected_tables, mysql_database=mysql_database,
        hive_database=hive_database, retriever=retriever)
    server = Server("house-price-tools")
    descriptions = {
        "search_policy": "检索北京政策原文及可核查元数据。",
        "read_policy_clause": "读取指定政策条款原文。",
        "lookup_metric_definition": "查询业务指标定义与歧义状态。",
        "get_mysql_schema": "查看本轮允许的 MySQL Agent 视图及列。",
        "get_hive_schema": "查看本轮允许的 Hive Agent 视图及列。",
        "query_mysql_readonly": "执行受控 MySQL 只读 SQL。",
        "query_hive_readonly": "执行受控 Hive 只读 SQL。",
    }

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [types.Tool(name=name, description=descriptions[name],
            inputSchema=registry.get(name).input_model.model_json_schema())
            for name in registry.names]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict):
        # Pydantic performs the sole argument validation so errors keep existing codes.
        return registry.invoke(name, arguments).model_dump(mode="json")

    return server


async def _serve() -> None:
    source = os.environ.get("HOUSE_MCP_SOURCE", "")
    tables = set(filter(None, os.environ.get("HOUSE_MCP_TABLES", "").split(",")))
    settings = Settings()
    mysql_database = MysqlQueryDatabase(settings) if source != "policy" else None
    try:
        server = create_server(settings=settings, source=source, selected_tables=tables,
            mysql_database=mysql_database)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        if mysql_database is not None:
            mysql_database.close()


def main() -> None:
    import anyio
    anyio.run(_serve)


if __name__ == "__main__":
    main()
