from __future__ import annotations

from pyhive import hive

from app.config import Settings

HIVE_ALLOWED_COLUMNS: dict[str, tuple[str, ...]] = {
    "v_agent_house_info_analysis": (
        "source_record_id", "listing_type", "title", "city", "district", "community",
        "total_price", "unit_price", "monthly_rent", "area", "bedroom_count",
        "living_room_count", "layout", "orientation", "floor_level",
        "total_floors", "decoration", "listing_date", "data_source",
        "source_import_task_id", "dataset_id", "listing_month",
    ),
    "v_agent_house_data_quality_summary": (
        "total_rows", "valid_rows", "sale_rows", "rent_rows", "missing_location_rows",
        "invalid_price_rows", "invalid_area_rows", "duplicate_source_rows",
        "quality_score", "dataset_id", "import_task_id",
    ),
}

HIVE_TABLE_DESCRIPTIONS = {
    "v_agent_house_info_analysis": "当前已激活数据集的出售与出租挂牌明细，用于离线趋势和批量统计。",
    "v_agent_house_data_quality_summary": "当前已激活 CSV 数据集的数据质量统计。",
}


class HiveQueryDatabase:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def allowed_tables(self) -> set[str]:
        return set(HIVE_ALLOWED_COLUMNS)

    def _connect(self):
        return hive.Connection(
            host=self._settings.hive_host,
            port=self._settings.hive_port,
            username=self._settings.hive_username,
            database=self._settings.hive_database,
            auth=self._settings.hive_auth,
        )

    def describe_allowed_schema(self) -> str:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            sections: list[str] = []
            for table_name, allowed_columns in HIVE_ALLOWED_COLUMNS.items():
                cursor.execute(f"DESCRIBE {table_name}")
                discovered = {
                    row[0].strip().lower(): row[1]
                    for row in cursor.fetchall()
                    if row and row[0] and not row[0].startswith("#")
                }
                missing = set(allowed_columns) - set(discovered)
                if missing:
                    raise RuntimeError(
                        f"Hive table {table_name} is missing expected columns: {sorted(missing)}"
                    )
                rendered = ", ".join(
                    f"{column} {discovered[column]}" for column in allowed_columns
                )
                sections.append(
                    f"TABLE {table_name}\nDESCRIPTION: {HIVE_TABLE_DESCRIPTIONS[table_name]}\nCOLUMNS: {rendered}"
                )
            return "\n\n".join(sections)
        finally:
            connection.close()

    def execute_read_only(self, sql: str) -> tuple[list[str], list[list[object]]]:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(sql)
            columns = [description[0] for description in cursor.description or []]
            rows = [list(row) for row in cursor.fetchmany(self._settings.sql_max_rows)]
            return columns, rows
        finally:
            connection.close()
