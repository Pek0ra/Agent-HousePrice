from __future__ import annotations

from pyhive import hive

from app.config import Settings

HIVE_ALLOWED_COLUMNS: dict[str, tuple[str, ...]] = {
    "house_info_analysis": (
        "source_record_id", "title", "city", "district", "community",
        "total_price", "unit_price", "area", "bedroom_count",
        "living_room_count", "layout", "orientation", "floor_level",
        "total_floors", "decoration", "listing_date", "data_source",
        "import_task_id", "listing_month",
    ),
    "house_data_quality_summary": (
        "total_rows", "valid_rows", "missing_location_rows",
        "invalid_price_rows", "invalid_area_rows", "duplicate_source_rows",
        "quality_score", "import_date", "import_task_id",
    ),
}

HIVE_TABLE_DESCRIPTIONS = {
    "house_info_analysis": "历史出售房挂牌明细，按 listing_month 分区，用于离线趋势和批量统计。",
    "house_data_quality_summary": "CSV 导入批次的数据质量统计。",
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
