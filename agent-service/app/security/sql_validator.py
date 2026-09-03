import re

from sqlglot import exp, parse
from sqlglot.errors import ParseError


class UnsafeSqlError(ValueError):
    pass


class SqlValidator:
    _FORBIDDEN_PATTERN = re.compile(
        r"(--|/\*|\*/|\bINTO\s+OUTFILE\b|\bINTO\s+DUMPFILE\b|"
        r"\bLOAD_FILE\s*\(|\bSLEEP\s*\(|\bBENCHMARK\s*\(|\bGET_LOCK\s*\(|"
        r"\bRELEASE_LOCK\s*\(|@@)",
        re.IGNORECASE,
    )

    def __init__(self, allowed_tables: set[str], max_rows: int = 100) -> None:
        self._allowed_tables = {table.lower() for table in allowed_tables}
        self._max_rows = max_rows

    def validate_and_normalize(self, sql: str) -> str:
        candidate = sql.strip().rstrip(";").strip()
        if not candidate:
            raise UnsafeSqlError("SQL is empty")
        if self._FORBIDDEN_PATTERN.search(candidate):
            raise UnsafeSqlError("SQL contains a forbidden construct")

        try:
            statements = parse(candidate, read="mysql")
        except ParseError as exc:
            raise UnsafeSqlError(f"SQL cannot be parsed: {exc}") from exc

        if len(statements) != 1 or statements[0] is None:
            raise UnsafeSqlError("Exactly one SQL statement is required")
        statement = statements[0]
        if not isinstance(statement, exp.Query):
            raise UnsafeSqlError("Only SELECT queries are allowed")

        forbidden_node_types = (
            exp.DDL,
            exp.DML,
            exp.Command,
            exp.Grant,
            exp.Revoke,
            exp.Transaction,
            exp.Lock,
            exp.Into,
        )
        if any(
            isinstance(node, forbidden_node_types)
            for node in statement.walk()
            if node is not statement
        ):
            raise UnsafeSqlError("SQL contains a forbidden operation")

        cte_names = {
            cte.alias_or_name.lower()
            for cte in statement.find_all(exp.CTE)
            if cte.alias_or_name
        }
        table_nodes = list(statement.find_all(exp.Table))
        if any(table.db or table.catalog for table in table_nodes):
            raise UnsafeSqlError("Qualified cross-database table names are not allowed")
        referenced_tables = {
            table.name.lower()
            for table in table_nodes
            if table.name.lower() not in cte_names
        }
        if not referenced_tables:
            raise UnsafeSqlError("A query must read from an allowed table")
        forbidden_tables = referenced_tables - self._allowed_tables
        if forbidden_tables:
            raise UnsafeSqlError(
                f"Query references forbidden tables: {sorted(forbidden_tables)}"
            )

        for star in statement.find_all(exp.Star):
            if not isinstance(star.parent, exp.Count):
                raise UnsafeSqlError("SELECT * is not allowed")

        limit = statement.args.get("limit")
        if limit is None:
            statement = statement.limit(self._max_rows)
        else:
            limit_expression = limit.expression
            if not isinstance(limit_expression, exp.Literal) or not limit_expression.is_int:
                raise UnsafeSqlError("LIMIT must be a fixed integer")
            if int(limit_expression.this) > self._max_rows:
                statement.set("limit", exp.Limit(expression=exp.Literal.number(self._max_rows)))

        return statement.sql(dialect="mysql")
