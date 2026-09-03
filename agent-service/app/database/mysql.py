from __future__ import annotations

from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine

from app.config import Settings

ALLOWED_COLUMNS: dict[str, tuple[str, ...]] = {
    "v_agent_house_listing": (
        "listing_type", "city", "district", "community", "total_price",
        "unit_price", "monthly_rent", "area", "bedroom_count",
        "living_room_count", "layout", "listing_date", "data_source",
    ),
    "v_agent_district_summary": (
        "listing_type", "city", "district", "listing_count", "avg_total_price",
        "min_total_price", "max_total_price", "avg_unit_price", "min_unit_price",
        "max_unit_price", "avg_monthly_rent", "min_monthly_rent",
        "max_monthly_rent",
    ),
    "v_agent_monthly_price_trend": (
        "listing_type", "city", "district", "listing_month", "listing_count",
        "avg_total_price", "avg_unit_price", "avg_monthly_rent",
    ),
}

TABLE_DESCRIPTIONS = {
    "v_agent_house_listing": "清洗后的售房与租房挂牌明细；listing_type 为 SALE 或 RENT。",
    "v_agent_district_summary": "按城市、行政区和挂牌类型预聚合的数量、均值、最小值和最大值。",
    "v_agent_monthly_price_trend": "按城市、行政区、挂牌类型和自然月预聚合的价格趋势。",
}


class MysqlQueryDatabase:
    def __init__(self, settings: Settings, engine: Engine | None = None) -> None:
        self._settings = settings
        self._engine = engine or create_engine(
            URL.create(
                drivername="mysql+pymysql",
                username=settings.mysql_username,
                password=settings.mysql_password,
                host=settings.mysql_host,
                port=settings.mysql_port,
                database=settings.mysql_database,
                query={"charset": "utf8mb4"},
            ),
            pool_pre_ping=True,
            pool_recycle=1800,
        )

    @property
    def allowed_tables(self) -> set[str]:
        return set(ALLOWED_COLUMNS)

    def describe_allowed_schema(self) -> str:
        requested_tables = tuple(ALLOWED_COLUMNS)
        placeholders = ", ".join(f":table_{index}" for index in range(len(requested_tables)))
        params = {f"table_{index}": name for index, name in enumerate(requested_tables)}
        params["schema_name"] = self._settings.mysql_database
        schema_sql = text(
            "SELECT table_name, column_name, column_type "
            "FROM information_schema.columns "
            "WHERE table_schema = :schema_name "
            f"AND table_name IN ({placeholders}) "
            "ORDER BY table_name, ordinal_position"
        )
        with self._engine.connect() as connection:
            rows = connection.execute(schema_sql, params).all()
        discovered: dict[str, dict[str, str]] = {name: {} for name in requested_tables}
        for table_name, column_name, column_type in rows:
            discovered[table_name][column_name] = column_type

        sections: list[str] = []
        for table_name, allowed_columns in ALLOWED_COLUMNS.items():
            actual_columns = discovered[table_name]
            missing = set(allowed_columns) - set(actual_columns)
            if missing:
                raise RuntimeError(
                    f"Table {table_name} is missing expected columns: {sorted(missing)}"
                )
            rendered_columns = ", ".join(
                f"{name} {actual_columns[name]}" for name in allowed_columns
            )
            sections.append(
                f"TABLE {table_name}\nDESCRIPTION: {TABLE_DESCRIPTIONS[table_name]}\n"
                f"COLUMNS: {rendered_columns}"
            )
        return "\n\n".join(sections)

    def execute_read_only(self, sql: str) -> tuple[list[str], list[list[object]]]:
        with self._engine.connect() as connection:
            connection.exec_driver_sql(
                f"SET SESSION MAX_EXECUTION_TIME = {self._settings.sql_execution_timeout_ms}"
            )
            result = connection.execute(text(sql))
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchmany(self._settings.sql_max_rows)]
        return columns, rows
