import pytest

from app.security.sql_validator import SqlValidator, UnsafeSqlError


@pytest.fixture
def validator() -> SqlValidator:
    return SqlValidator(
        {
            "v_agent_house_listing",
            "v_agent_district_summary",
            "v_agent_monthly_price_trend",
        },
        max_rows=100,
    )


def test_allows_aggregate_query_and_adds_limit(validator: SqlValidator) -> None:
    sql = validator.validate_and_normalize(
        "SELECT district, ROUND(AVG(unit_price), 2) AS avg_unit_price "
        "FROM v_agent_house_listing GROUP BY district ORDER BY avg_unit_price DESC"
    )

    assert "LIMIT 100" in sql
    assert "AVG(unit_price)" in sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM v_agent_house_listing",
        "SELECT * FROM v_agent_house_listing",
        "SELECT id FROM house_info",
        "SELECT city FROM v_agent_house_listing; DROP TABLE house_info",
        "SELECT SLEEP(10) FROM v_agent_house_listing",
        "SELECT city INTO OUTFILE '/tmp/data' FROM v_agent_house_listing",
        "SELECT city FROM v_agent_house_listing FOR UPDATE",
        "SELECT city FROM another_database.v_agent_house_listing",
    ],
)
def test_rejects_unsafe_queries(validator: SqlValidator, sql: str) -> None:
    with pytest.raises(UnsafeSqlError):
        validator.validate_and_normalize(sql)


def test_caps_excessive_limit(validator: SqlValidator) -> None:
    sql = validator.validate_and_normalize(
        "SELECT city FROM v_agent_house_listing LIMIT 1000"
    )

    assert "LIMIT 100" in sql


def test_allows_count_star(validator: SqlValidator) -> None:
    sql = validator.validate_and_normalize(
        "SELECT COUNT(*) AS listing_count FROM v_agent_house_listing"
    )

    assert "COUNT(*)" in sql
