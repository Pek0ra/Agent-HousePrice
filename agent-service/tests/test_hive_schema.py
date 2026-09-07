from app.database.hive import HIVE_ALLOWED_COLUMNS


def test_analysis_view_uses_source_import_task_id() -> None:
    columns = HIVE_ALLOWED_COLUMNS["v_agent_house_info_analysis"]

    assert "source_import_task_id" in columns
    assert "import_task_id" not in columns
