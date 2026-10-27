from __future__ import annotations

import pytest

from app.ask_data.physical_identifiers import qualified_physical_name, sqlglot_dialect


def test_sqlglot_dialect_mapping() -> None:
    assert sqlglot_dialect("trino") == "trino"
    assert sqlglot_dialect("postgres") == "postgres"
    assert sqlglot_dialect("impala") == "hive"
    assert sqlglot_dialect(None, legacy_data_backend="duckdb") == "duckdb"


def test_qualified_names() -> None:
    assert qualified_physical_name(
        connector_type="impala",
        catalog=None,
        schema="gold",
        table_name="sales_monthly",
        view_name=None,
    ) == "`gold`.`sales_monthly`"
    assert qualified_physical_name(
        connector_type="trino",
        catalog="hive",
        schema="gold",
        table_name="sales_monthly",
        view_name=None,
    ) == "`hive`.`gold`.`sales_monthly`"
    assert qualified_physical_name(
        connector_type="postgres",
        catalog=None,
        schema="public",
        table_name="sales_monthly",
        view_name=None,
    ) == "public.`sales_monthly`"


def test_trino_requires_catalog_schema() -> None:
    with pytest.raises(ValueError):
        qualified_physical_name(
            connector_type="trino",
            catalog=None,
            schema=None,
            table_name="t",
            view_name=None,
        )
