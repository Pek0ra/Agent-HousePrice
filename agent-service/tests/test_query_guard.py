import pytest

from app.agents.query_guard import ground_query, quality_scalar


def test_requested_district_aliases_are_grounded_before_execution():
    sql = "SELECT district, COUNT(*) FROM v_agent_house_listing WHERE city='北京市' AND district IN ('朝阳','海淀') AND listing_type='SALE' GROUP BY district"
    fixed = ground_query(sql, districts=["朝阳区", "海淀区"], source="mysql",
                         selected_tables=["v_agent_house_listing"], question="北京朝阳和海淀区出售样本各多少条")
    assert "'朝阳区'" in fixed and "'海淀区'" in fixed
    assert "'朝阳'" not in fixed and "'海淀'" not in fixed


def test_district_condition_cannot_silently_disappear_or_switch_region():
    for sql in (
        "SELECT COUNT(*) FROM v_agent_house_listing WHERE city='北京市'",
        "SELECT COUNT(*) FROM v_agent_house_listing WHERE district='西城区'",
    ):
        with pytest.raises(ValueError, match="地区条件与问题不一致"):
            ground_query(sql, districts=["海淀区"], source="mysql",
                         selected_tables=["v_agent_house_listing"], question="海淀区有多少条")


def test_simple_quality_count_keeps_zero_row():
    question = "当前激活导入批次的无效面积记录有多少条？"
    tables = ["v_agent_house_data_quality_summary"]
    assert quality_scalar(question, tables) == ("invalid_area_rows", "无效面积记录")
    fixed = ground_query("SELECT invalid_area_rows FROM v_agent_house_data_quality_summary WHERE invalid_area_rows > 0",
                         districts=[], source="hive", selected_tables=tables, question=question)
    assert fixed == "SELECT invalid_area_rows FROM v_agent_house_data_quality_summary"


def test_explicit_quality_threshold_is_not_removed():
    question = "无效面积记录超过 0 条的批次有多少？"
    sql = "SELECT invalid_area_rows FROM v_agent_house_data_quality_summary WHERE invalid_area_rows > 0"
    assert quality_scalar(question, ["v_agent_house_data_quality_summary"]) is None
    assert ground_query(sql, districts=[], source="hive",
                        selected_tables=["v_agent_house_data_quality_summary"], question=question) == sql
