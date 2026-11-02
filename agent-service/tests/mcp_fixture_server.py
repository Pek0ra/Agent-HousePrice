"""Subprocess fixture: exercises production MCP server with a database test double."""

import os

import anyio

from app.config import Settings
from app.database.hive import HIVE_ALLOWED_COLUMNS
from app.database.mysql import ALLOWED_COLUMNS
from app.mcp_server import create_server
from mcp.server.stdio import stdio_server


class Database:
    def __init__(self, columns):
        self.columns = columns
        self.allowed_tables = set(columns)

    def describe_allowed_schema(self):
        return "\n\n".join(f"TABLE {table}\nDESCRIPTION: test\nCOLUMNS: " +
            ", ".join(f"{column} DECIMAL" for column in columns)
            for table, columns in self.columns.items())

    def execute_read_only(self, sql):
        if "v_agent_monthly_price_trend" in sql:
            return ["listing_month", "avg_unit_price"], [["2026-01", 12000], ["2026-02", 12345]]
        if "v_agent_house_info_analysis" in sql:
            return ["unit_price"], [[8800]]
        if "LIMIT 2" in sql:
            return ["unit_price"], [[1], [2], [3]]
        return ["unit_price"], [[12345]]


async def main():
    source = os.environ["HOUSE_MCP_SOURCE"]
    tables = set(os.environ["HOUSE_MCP_TABLES"].split(","))
    server = create_server(settings=Settings(), source=source, selected_tables=tables,
        mysql_database=Database(ALLOWED_COLUMNS),
        hive_database=Database(HIVE_ALLOWED_COLUMNS))
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
