"""Registry-staged OSSIE catalog metric matching (@Semantic NL path)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.semantic.registry import TempoOssieRegistry, _is_semantic_registry_catalog


def _banking_registry(tmp_path: Path) -> TempoOssieRegistry:
    root = tmp_path / "banking_runtime"
    ossie = root / "ossie"
    ossie.mkdir(parents=True)
    (ossie / "tempo_core.ossie.yaml").write_text(
        """
version: "0.2.0.dev0"
name: banking_analytics
description: Banking demo
datasets:
  - name: customers
    source: banking_demo.customers
    primary_key: [customer_id]
    fields:
      - name: customer_id
        datatype: String
  - name: transactions
    source: banking_demo.transactions
    primary_key: [transaction_id]
    fields:
      - name: amount
        datatype: Decimal
metrics:
  - name: customers_customer_id_total
    description: Total Customer Count
    expression:
      dialects:
        - dialect: ANSI_SQL
          expression: COUNT(DISTINCT customer_id)
    custom_extensions:
      - vendor_name: TEMPO
        data: '{"base_dataset": "customers", "allowed_dimensions": []}'
  - name: total_transaction_amount
    description: Total Transaction Amount
    ai_context:
      synonyms: ["total amount", "transaction amount"]
    expression:
      dialects:
        - dialect: ANSI_SQL
          expression: SUM(amount)
    custom_extensions:
      - vendor_name: TEMPO
        data: '{"base_dataset": "transactions", "allowed_dimensions": []}'
""",
        encoding="utf-8",
    )
    (ossie / "tempo_governance.yaml").write_text(
        'unknown_metric_question: "Which metric would you like to report on?"\n',
        encoding="utf-8",
    )
    (ossie / "golden_questions.yaml").write_text("questions: []\n", encoding="utf-8")
    return TempoOssieRegistry(root, validate_profile=False)


def test_catalog_detector_skips_tempo_metrics() -> None:
    assert not _is_semantic_registry_catalog({"sat_dc_stock_quantity": {}})
    assert _is_semantic_registry_catalog({"total_transaction_amount": {}})


def test_catalog_resolves_customer_question(tmp_path: Path) -> None:
    reg = _banking_registry(tmp_path)
    hit = reg.resolve_metric("berapa total customer saat ini?")
    assert hit["status"] == "resolved"
    assert hit["metric"] == "customers_customer_id_total"


def test_catalog_resolves_transaction_amount(tmp_path: Path) -> None:
    reg = _banking_registry(tmp_path)
    hit = reg.resolve_metric("What is total transaction amount?")
    assert hit["status"] == "resolved"
    assert hit["metric"] == "total_transaction_amount"


def test_catalog_ambiguous_returns_picker(tmp_path: Path) -> None:
    reg = _banking_registry(tmp_path)
    hit = reg.resolve_metric("show me the numbers")
    assert hit["status"] == "needs_clarification"
    assert len(hit.get("options") or []) >= 2
