"""Registry-staged OSSIE catalog metric matching (@Semantic NL path)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.semantic.registry import OssieRegistry


def _registry(tmp_path: Path) -> OssieRegistry:
    root = tmp_path / "runtime"
    ossie = root / "ossie"
    ossie.mkdir(parents=True)
    (ossie / "reference_core.ossie.yaml").write_text(
        """
version: "0.2.0.dev0"
name: banking_analytics
description: Customers and transactions
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
      - vendor_name: REFERENCE
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
      - vendor_name: REFERENCE
        data: '{"base_dataset": "transactions", "allowed_dimensions": []}'
""",
        encoding="utf-8",
    )
    (ossie / "reference_governance.yaml").write_text(
        'unknown_metric_question: "Which metric would you like to report on?"\n',
        encoding="utf-8",
    )
    (ossie / "golden_questions.yaml").write_text("questions: []\n", encoding="utf-8")
    return OssieRegistry(root, validate_profile=False)


def test_a_question_without_an_alias_offers_the_closest_metric_first(tmp_path: Path) -> None:
    # The keyword matcher only resolves on an alias; the language model's metric choice handles the rest.
    reg = _registry(tmp_path)
    hit = reg.resolve_metric("berapa total customer saat ini?")
    assert hit["status"] == "needs_clarification"
    assert hit["options"][0]["id"] == "customers_customer_id_total"


def test_catalog_resolves_transaction_amount(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    hit = reg.resolve_metric("What is total transaction amount?")
    assert hit["status"] == "resolved"
    assert hit["metric"] == "total_transaction_amount"


def test_catalog_ambiguous_returns_picker(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    hit = reg.resolve_metric("show me the numbers")
    assert hit["status"] == "needs_clarification"
    assert len(hit.get("options") or []) >= 2
