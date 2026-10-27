"""Config-driven runtime extensions (not banking-specific)."""
from __future__ import annotations

from pathlib import Path

from app.semantic.registry import TempoOssieRegistry
from app.semantic.runtime_extensions import (
    load_profile,
    resolve_runtime_extensions,
    try_compile_governed_join_sql,
)


def test_profile_loads_banking_demo() -> None:
    prof = load_profile("banking_demo")
    assert "metric_enrichment" in prof
    assert "governed_joins" in prof


def test_auto_detect_profile_by_source_substring(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    ossie = root / "ossie"
    ossie.mkdir(parents=True)
    (ossie / "tempo_core.ossie.yaml").write_text(
        """
name: demo
datasets:
  - name: transactions
    source: acme_analytics.orders_fact
    fields: []
  - name: customers
    source: acme_analytics.customers_dim
    fields: []
metrics: []
""",
        encoding="utf-8",
    )
    (ossie / "tempo_governance.yaml").write_text("runtime_extensions:\n  profile: banking_demo\n", encoding="utf-8")
    (ossie / "golden_questions.yaml").write_text("questions: []\n", encoding="utf-8")
    reg = TempoOssieRegistry(root, validate_profile=False)
    assert reg.runtime_extensions is not None
    assert "transactions_failed_transaction_rate" in reg.metrics or "metric_enrichment" in reg.runtime_extensions


def test_governed_join_compile_uses_profile(tmp_path: Path) -> None:
    prof = load_profile("banking_demo")
    datasets = {
        "transactions": {"source": "banking_demo.transactions"},
        "customers": {"source": "banking_demo.customers"},
    }
    sql = try_compile_governed_join_sql(
        extensions=prof,
        datasets=datasets,
        metric_base_dataset="transactions",
        metric_expression="COUNT(transaction_id)",
        question="Top 5 customer segment berdasarkan jumlah transaksi.",
        row_filter=None,
        period_predicate=None,
        extra_predicates=None,
        sql_max_rows=200,
    )
    assert sql
    assert "JOIN" in sql.upper()
    assert "COUNT(d.transaction_id)" in sql or "COUNT( d.transaction_id)" in sql.replace(" ", "")


def test_resolve_inline_governance_overrides_profile() -> None:
    base = load_profile("banking_demo")
    merged = resolve_runtime_extensions(
        {"runtime_extensions": {"profile": "banking_demo", "breakdown": {"cues": ["custom_cue"]}}},
        {"transactions": {"source": "banking_demo.transactions"}},
    )
    assert merged is not None
    assert merged.get("breakdown", {}).get("cues") == ["custom_cue"]
    assert base.get("metric_enrichment")
