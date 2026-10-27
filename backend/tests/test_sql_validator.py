from app.semantic.context import SemanticContextService
from app.sql.validator import validate_sql


def test_validator_accepts_readonly_approved_query() -> None:
    result = validate_sql(
        """
        SELECT d.material, SUM(d.sell_in_bill_val) AS sell_in
        FROM gold.rpt_sap_material_month_semantic d
        WHERE d.calmonth = 202412
        GROUP BY d.material
        ORDER BY sell_in DESC
        LIMIT 10
        """,
        SemanticContextService(),
    )

    assert result.valid is True
    assert result.sql is not None
    assert "LIMIT 10" in result.sql


def test_validator_rejects_allowed_column_on_wrong_table() -> None:
    result = validate_sql(
        "SELECT d.dcname FROM gold.rpt_sap_material_month_semantic d LIMIT 10",
        SemanticContextService(),
    )

    assert result.valid is False
    assert result.error == "Column not allowed for gold.rpt_sap_material_month_semantic: dcname"


def test_validator_rejects_write_or_multiple_statements() -> None:
    context = SemanticContextService()
    assert validate_sql("DROP TABLE gold.x", context).error == "DDL/DML statements are not allowed"
    assert validate_sql("SELECT 1; SELECT 2", context).error == "Only one SQL statement is allowed"


def test_validator_rejects_star_and_caps_limit() -> None:
    context = SemanticContextService()
    star = validate_sql("SELECT * FROM gold.rpt_sap_material_month_semantic LIMIT 10", context)
    capped = validate_sql(
        "SELECT d.material FROM gold.rpt_sap_material_month_semantic d LIMIT 9999",
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
        "SELECT REFLECT('java.lang.Runtime', 'getRuntime') FROM gold.rpt_sap_material_month_semantic LIMIT 1",
        context,
    )
    accepted = validate_sql(
        "SELECT SUM(d.sell_in_bill_val) AS total FROM gold.rpt_sap_material_month_semantic d LIMIT 1",
        context,
    )

    assert rejected.valid is False
    assert rejected.error == "Function not allowed: reflect"
    assert accepted.valid is True
