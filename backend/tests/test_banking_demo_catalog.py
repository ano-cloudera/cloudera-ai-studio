"""Auto-imported banking_demo OSSIE enrichment and NL resolution."""
from __future__ import annotations

from pathlib import Path

from app.semantic.registry import TempoOssieRegistry


def _auto_banking_ossie(tmp_path: Path) -> TempoOssieRegistry:
    root = tmp_path / "runtime"
    ossie = root / "ossie"
    ossie.mkdir(parents=True)
    (ossie / "tempo_core.ossie.yaml").write_text(
        """
version: "0.2.0.dev0"
name: banking_analytics
datasets:
  - name: customers
    source: banking_demo.customers
    fields:
      - name: customers_join_date
        dimension: {}
      - name: customers_segment
        expression:
          dialects:
            - dialect: ANSI_SQL
              expression: segment
        dimension: {}
      - name: customer_id
        dimension: {}
  - name: transactions
    source: banking_demo.transactions
    fields:
      - name: transactions_transaction_date
        dimension: {}
      - name: transaction_id
        dimension: {}
      - name: amount
        dimension: {}
      - name: transactions_channel
        expression:
          dialects:
            - dialect: ANSI_SQL
              expression: channel
        dimension: {}
metrics:
  - name: customers_customer_id_total
    description: Suggested metric customers_customer_id_total
    expression:
      dialects:
        - dialect: ANSI_SQL
          expression: SUM(customer_id)
    custom_extensions:
      - vendor_name: TEMPO
        data: '{"base_dataset": "customers", "allowed_dimensions": ["customers_join_date", "customers_segment"]}'
  - name: transactions_transaction_id_total
    description: Suggested metric transactions_transaction_id_total
    expression:
      dialects:
        - dialect: ANSI_SQL
          expression: SUM(transaction_id)
    custom_extensions:
      - vendor_name: TEMPO
        data: '{"base_dataset": "transactions", "allowed_dimensions": ["transactions_transaction_date"]}'
  - name: transactions_amount_total
    description: Suggested metric transactions_amount_total
    expression:
      dialects:
        - dialect: ANSI_SQL
          expression: SUM(amount)
    custom_extensions:
      - vendor_name: TEMPO
        data: '{"base_dataset": "transactions", "allowed_dimensions": ["transactions_transaction_date", "transactions_channel"]}'
""",
        encoding="utf-8",
    )
    (ossie / "tempo_governance.yaml").write_text("{}", encoding="utf-8")
    (ossie / "golden_questions.yaml").write_text("questions: []\n", encoding="utf-8")
    return TempoOssieRegistry(root, validate_profile=False)


def test_banking_enrichment_uses_count_distinct_for_customers(tmp_path: Path) -> None:
    reg = _auto_banking_ossie(tmp_path)
    definition = reg.metric_definition("customers_customer_id_total")
    assert "COUNT(DISTINCT customer_id)" in definition["expression"]
    assert reg.dataset_fields["transactions"]["transactions_transaction_date"]["dimension"].get("is_time")


def test_banking_resolves_total_customer_indonesian(tmp_path: Path) -> None:
    reg = _auto_banking_ossie(tmp_path)
    hit = reg.resolve_metric("berapa total customer kita saat ini ?")
    assert hit["status"] == "resolved"
    assert hit["metric"] == "customers_customer_id_total"


def test_banking_resolves_transaction_trend_without_clarification(tmp_path: Path) -> None:
    reg = _auto_banking_ossie(tmp_path)
    q = "coba jelaskan pertumbuhan trend jumlah transaksi per bulan (12 bulan terakhir)"
    hit = reg.resolve_metric(q)
    assert hit["status"] == "resolved"
    assert hit["metric"] == "transactions_transaction_id_total"


def test_banking_breakdown_by_tipe_akun_compiles_group_by(tmp_path: Path) -> None:
    from app.semantic.context import SemanticContextService

    _auto_banking_ossie(tmp_path)
    ctx = SemanticContextService(tmp_path / "runtime", validate_profile=False)
    sql = ctx.compile_governed(
        "customers_customer_id_total",
        "Bandingkan jumlah customer per tipe akun.",
    )
    assert "GROUP BY" in sql
    assert "customers_segment" in sql or "segment" in sql.casefold()
    assert "COUNT(DISTINCT customer_id)" in sql


def test_banking_resolves_failed_transaction_rate(tmp_path: Path) -> None:
    reg = _auto_banking_ossie(tmp_path)
    hit = reg.resolve_metric("Berapa failed transaction rate?")
    assert hit["status"] == "resolved"
    assert hit["metric"] == "transactions_failed_transaction_rate"


def test_banking_join_sql_passes_validation(tmp_path: Path) -> None:
    from app.ask_data.validation import validate_ask_data_sql
    from app.semantic.banking_demo_catalog import banking_governed_join_state_patch
    from app.semantic.context import SemanticContextService

    reg = _auto_banking_ossie(tmp_path)
    ctx = SemanticContextService(tmp_path / "runtime", validate_profile=False)
    sql = ctx.compile_governed(
        "transactions_transaction_id_total",
        "Top 5 customer segment berdasarkan jumlah transaksi.",
    )
    patch = banking_governed_join_state_patch(reg.datasets, sql, {"legacy_fallback": False, "dialect": "hive"})
    assert patch is not None
    ok = validate_ask_data_sql(sql, ctx, state=patch, max_rows=200)
    assert ok.valid, ok.error


def test_configured_starters_override_capability_lines(tmp_path: Path) -> None:
    from app.semantic.context import SemanticContextService

    _auto_banking_ossie(tmp_path)
    ctx = SemanticContextService(tmp_path / "runtime", validate_profile=False)
    lines = ctx.domain_capability_insight_lines(
        configured_starters=["Berapa total customer kita saat ini?"],
    )
    assert len(lines) == 1
    assert "total customer" in lines[0].casefold()
    assert "TEMPO" not in lines[0]
    assert "Sell-In" not in lines[0]


def test_banking_capability_insights_not_tempo_catalog(tmp_path: Path) -> None:
    from app.semantic.context import SemanticContextService

    _auto_banking_ossie(tmp_path)
    ctx = SemanticContextService(tmp_path / "runtime", validate_profile=False)
    lines = ctx.domain_capability_insight_lines()
    assert lines
    assert not any("Sell-In" in line or "Stock Tempo" in line or "Alfamart" in line for line in lines)
    assert any("customer" in line.casefold() or "Customer" in line for line in lines)
    assert all("Contoh:" in line for line in lines)


def test_banking_top_customer_by_amount_groups_by_customer_id(tmp_path: Path) -> None:
    from app.semantic.context import SemanticContextService

    _auto_banking_ossie(tmp_path)
    ctx = SemanticContextService(tmp_path / "runtime", validate_profile=False)
    resolution = ctx.resolve("Top 10 customer berdasarkan total nominal transaksi.")
    assert resolution.get("status") == "resolved"
    assert resolution.get("metric") == "transactions_amount_total"
    sql = ctx.compile_governed(
        str(resolution["metric"]),
        "Top 10 customer berdasarkan total nominal transaksi.",
    )
    assert "GROUP BY" in sql.upper()
    assert "customer_id" in sql.casefold()
    assert "SUM" in sql.upper()
    assert "LIMIT 10" in sql


def test_banking_top_segment_by_transactions_uses_customer_join(tmp_path: Path) -> None:
    from app.semantic.context import SemanticContextService

    _auto_banking_ossie(tmp_path)
    ctx = SemanticContextService(tmp_path / "runtime", validate_profile=False)
    sql = ctx.compile_governed(
        "transactions_transaction_id_total",
        "Top 5 customer segment berdasarkan jumlah transaksi.",
    )
    assert "JOIN" in sql.upper()
    assert "customers" in sql.casefold()
    assert "segment" in sql.casefold()
    assert "LIMIT 5" in sql


def test_banking_resolves_channel_highest_value_with_amount_metric(tmp_path: Path) -> None:
    from app.semantic.context import SemanticContextService

    _auto_banking_ossie(tmp_path)
    ctx = SemanticContextService(tmp_path / "runtime", validate_profile=False)
    resolution = ctx.resolve("Which channel had the highest value?")
    assert resolution.get("status") == "resolved"
    assert resolution.get("metric") == "transactions_amount_total"
    assert "transactions_channel" in (resolution.get("dimensions") or [])


def test_banking_breakdown_by_channel_uses_session_last_metric(tmp_path: Path) -> None:
    from app.semantic.context import SemanticContextService

    _auto_banking_ossie(tmp_path)
    ctx = SemanticContextService(tmp_path / "runtime", validate_profile=False)
    session = {"last_metric": "transactions_amount_total", "last_dimensions": []}
    bare = ctx.resolve("Break it down by channel.")
    assert bare.get("status") == "resolved"
    assert bare.get("metric") == "transactions_amount_total"
    continued = ctx.resolve(
        "Break it down by channel.",
        session_analysis_context=session,
    )
    assert continued.get("status") == "resolved"
    assert continued.get("metric") == "transactions_amount_total"
    assert "transactions_channel" in (continued.get("dimensions") or [])


def test_banking_picker_labels_are_humanized(tmp_path: Path) -> None:
    reg = _auto_banking_ossie(tmp_path)
    hit = reg.resolve_metric("show me numbers")
    assert hit["status"] == "needs_clarification"
    names = [opt["name"] for opt in hit.get("options") or []]
    assert any("Transaction Count" in n or "Total Customers" in n for n in names)
    assert not any(n.startswith("Suggested metric") for n in names)
