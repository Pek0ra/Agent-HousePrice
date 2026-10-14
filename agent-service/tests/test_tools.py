import pytest

from app.config import Settings
from app.database.hive import HIVE_ALLOWED_COLUMNS
from app.database.mysql import ALLOWED_COLUMNS
from app.tools import build_tool_registry
from app.tools.contracts import MetricLookupOutput, QueryOutput, SchemaOutput


class FakeDatabase:
    def __init__(self, columns):
        self.allowed_tables = set(columns)
        self.columns = columns
        self.executed = []
        self.rows = [[1]]
        self.failure = None

    def describe_allowed_schema(self):
        if self.failure:
            raise self.failure
        return "\n\n".join(
            f"TABLE {name}\nDESCRIPTION: test\nCOLUMNS: "
            + ", ".join(f"{column} decimal(10, 2)" for column in names)
            for name, names in self.columns.items()
        )

    def execute_read_only(self, sql):
        self.executed.append(sql)
        if self.failure:
            raise self.failure
        return ["value"], self.rows


@pytest.fixture
def databases():
    return FakeDatabase(ALLOWED_COLUMNS), FakeDatabase(HIVE_ALLOWED_COLUMNS)


def registry(databases, source="mysql", enabled=False, selected=None, max_rows=3):
    mysql, hive = databases
    return build_tool_registry(
        settings=Settings(big_data_enabled=enabled, sql_max_rows=max_rows),
        source=source,
        selected_tables=selected or ({"v_agent_house_info_analysis"} if source == "hive" else {"v_agent_house_listing"}),
        mysql_database=mysql,
        hive_database=hive,
    )


def test_metric_lookup_contract_and_ambiguity(databases):
    tools = registry(databases)
    result = tools.invoke("lookup_metric_definition", {"question": "哪个区性价比最高？"})
    assert result.ok and isinstance(result.data, MetricLookupOutput)
    assert result.data.definitions[0].id == "value_for_money"
    assert result.data.needs_clarification and result.data.clarification_question
    for arguments in ({}, {"question": ""}, {"question": "房价", "database": "hive"}, {"question": 42}):
        assert tools.invoke("lookup_metric_definition", arguments).error.code == "invalid_arguments"


def test_schema_only_exposes_selected_view_and_columns(databases):
    tools = registry(databases)
    result = tools.invoke("get_mysql_schema", {})
    assert result.ok and isinstance(result.data, SchemaOutput)
    assert result.data.source == "mysql"
    assert [view.name for view in result.data.views] == ["v_agent_house_listing"]
    assert [column.name for column in result.data.views[0].columns] == list(ALLOWED_COLUMNS["v_agent_house_listing"])
    assert result.data.views[0].columns[0].type == "decimal(10, 2)"
    assert tools.invoke("get_mysql_schema", {"table": "v_agent_district_summary"}).error.code == "invalid_arguments"
    assert tools.invoke("get_hive_schema", {}).error.code == "unavailable"


def test_capability_and_source_scope(databases):
    with pytest.raises(ValueError):
        registry(databases, source="hive")
    with pytest.raises(ValueError):
        registry(databases, selected={"house_info"})
    with pytest.raises(ValueError):
        registry(databases, source="hive", enabled=True, selected={"v_agent_house_listing"})
    mysql_tools = registry(databases, enabled=True)
    assert mysql_tools.names == ("lookup_metric_definition", "get_mysql_schema", "query_mysql_readonly")
    assert mysql_tools.invoke("query_hive_readonly", {"sql": "SELECT city FROM v_agent_house_info_analysis"}).error.code == "unavailable"
    hive_tools = registry(databases, source="hive", enabled=True)
    assert hive_tools.names == ("lookup_metric_definition", "get_hive_schema", "query_hive_readonly")
    assert hive_tools.invoke("get_hive_schema", {}).data.views[0].name == "v_agent_house_info_analysis"
    assert hive_tools.invoke("query_mysql_readonly", {"sql": "SELECT city FROM v_agent_house_listing"}).error.code == "unavailable"


@pytest.mark.parametrize("source,table,other", [
    ("mysql", "v_agent_house_listing", "v_agent_district_summary"),
    ("hive", "v_agent_house_info_analysis", "v_agent_house_data_quality_summary"),
])
def test_direct_query_call_enforces_sql_validation(databases, source, table, other):
    tools = registry(databases, source=source, enabled=True)
    name = f"query_{source}_readonly"
    for sql in (
        f"DELETE FROM {table}",
        f"SELECT city FROM another_database.{table}",
        f"SELECT city FROM {other}",
        f"SELECT * FROM {table}",
        f"SELECT city FROM {table}; DROP TABLE {table}",
    ):
        result = tools.invoke(name, {"sql": sql})
        assert not result.ok and result.error.code == "unsafe_sql"
    assert not databases[0].executed and not databases[1].executed
    for arguments in ({}, {"sql": ""}, {"sql": f"SELECT city FROM {table}", "database": "other"}):
        assert tools.invoke(name, arguments).error.code == "invalid_arguments"


@pytest.mark.parametrize("source,table", [
    ("mysql", "v_agent_house_listing"),
    ("hive", "v_agent_house_info_analysis"),
])
def test_query_is_bounded_and_adapter_errors_are_redacted(databases, source, table):
    tools = registry(databases, source=source, enabled=True)
    database = databases[1] if source == "hive" else databases[0]
    database.rows = [[i] for i in range(10)]
    name = f"query_{source}_readonly"
    result = tools.invoke(name, {"sql": f"SELECT city FROM {table} LIMIT 500"})
    assert result.ok and isinstance(result.data, QueryOutput)
    assert result.data.row_count == 3 and result.data.rows == [[0], [1], [2]]
    assert "LIMIT 3" in database.executed[0]
    database.failure = RuntimeError("secret_password@private-host")
    result = tools.invoke(name, {"sql": f"SELECT city FROM {table}"})
    assert result.error.code == "execution_failed"
    assert "secret_password" not in result.model_dump_json()
    assert tools.invoke(f"get_{source}_schema", {}).error.code == "execution_failed"


def test_metric_retrieval_error_is_redacted(databases):
    class BrokenRetriever:
        def retrieve(self, question):
            raise RuntimeError("secret_password@private-host")

    mysql, hive = databases
    tools = build_tool_registry(
        settings=Settings(), source="mysql", selected_tables={"v_agent_house_listing"},
        mysql_database=mysql, hive_database=hive, retriever=BrokenRetriever(),
    )
    result = tools.invoke("lookup_metric_definition", {"question": "房价"})
    assert result.error.code == "execution_failed"
    assert "secret_password" not in result.model_dump_json()

