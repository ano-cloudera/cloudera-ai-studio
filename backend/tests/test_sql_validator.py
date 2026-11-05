from app.semantic.context import SemanticContextService
from app.sql.validator import validate_sql


def test_validator_accepts_readonly_approved_query() -> None:
    result = validate_sql(
        """
        SELECT d.region_name, SUM(d.order_value) AS order_value
        FROM "hive"."default"."fulfillment_orders" d
        WHERE d.order_status = 'Delivered'
        GROUP BY d.region_name
        ORDER BY order_value DESC
        LIMIT 10
        """,
        SemanticContextService(),
    )

    assert result.valid is True
    assert result.sql is not None
    assert "LIMIT 10" in result.sql


def test_validator_rejects_allowed_column_on_wrong_table() -> None:
    result = validate_sql(
        'SELECT d.carrier FROM "hive"."default"."fulfillment_orders" d LIMIT 10',
        SemanticContextService(),
    )

    assert result.valid is False
    assert result.error == "Column not allowed for hive.default.fulfillment_orders: carrier"


def test_validator_rejects_write_or_multiple_statements() -> None:
    context = SemanticContextService()
    assert validate_sql("DROP TABLE gold.x", context).error == "DDL/DML statements are not allowed"
    assert validate_sql("SELECT 1; SELECT 2", context).error == "Only one SQL statement is allowed"


def test_validator_rejects_star_and_caps_limit() -> None:
    context = SemanticContextService()
    star = validate_sql('SELECT * FROM "hive"."default"."fulfillment_orders" LIMIT 10', context)
    capped = validate_sql(
        'SELECT d.region_name FROM "hive"."default"."fulfillment_orders" d LIMIT 9999',
        context,
        max_rows=200,
    )

    assert star.error == "SELECT * is not allowed"
    assert capped.valid is True
    assert capped.sql is not None
    assert "LIMIT 200" in capped.sql


def test_validator_rejects_unapproved_functions() -> None:
    context = SemanticContextService()
    rejected = validate_sql(
        "SELECT REFLECT('java.lang.Runtime', 'getRuntime') FROM \"hive\".\"default\".\"fulfillment_orders\" LIMIT 1",
        context,
    )
    accepted = validate_sql(
        'SELECT SUM(d.order_value) AS total FROM "hive"."default"."fulfillment_orders" d LIMIT 1',
        context,
    )

    assert rejected.valid is False
    assert rejected.error == "Function not allowed: reflect"
    assert accepted.valid is True


def test_count_star_is_an_aggregate_not_a_select_star() -> None:
    import sqlglot

    from app.sql.validator import has_projected_star

    assert has_projected_star(sqlglot.parse_one("SELECT COUNT(*) AS n FROM t")) is False
    assert has_projected_star(sqlglot.parse_one("SELECT region, COUNT(*) AS n FROM t GROUP BY region")) is False
    assert has_projected_star(sqlglot.parse_one("SELECT * FROM t")) is True
    assert has_projected_star(sqlglot.parse_one("SELECT t.* FROM t")) is True
    assert has_projected_star(sqlglot.parse_one("SELECT COUNT(*), * FROM t")) is True
