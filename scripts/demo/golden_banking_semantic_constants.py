"""Golden Banking Demo — Phase 3 semantic layer constants."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MODEL_NAME = "Retail Banking Analytics"
MODEL_KEY = "retail_banking_analytics"
MODEL_DESCRIPTION = (
    "Governed semantic model for Golden Banking customer and transaction analytics."
)

BANKING_SCHEMA = "banking_demo"
CUSTOMERS_TABLE = "customers"
TRANSACTIONS_TABLE = "transactions"

ENTITY_CUSTOMERS_KEY = "customers"
ENTITY_TRANSACTIONS_KEY = "transactions"

EVIDENCE_DIR = ROOT / "testing" / "evidence" / "golden-path" / "PHASE3-SEMANTIC"
REGISTRATION_EVIDENCE = EVIDENCE_DIR / "semantic-registration.json"

REQUIRED_METRIC_KEYS = (
    "total_transaction_amount",
    "transaction_count",
    "average_transaction_value",
    "active_customers",
    "failed_transaction_rate",
)

OPTIONAL_METRIC_KEYS = (
    "failed_transaction_count",
    "successful_transaction_count",
)

REQUIRED_DIMENSION_KEYS = (
    "transaction_month",
    "transaction_type",
    "channel",
    "merchant_category",
    "status",
    "segment",
    "city",
    "risk_tier",
    "customer_status",
)

GLOSSARY_SPECS = (
    {
        "key": "priority_customer",
        "term": "Priority Customer",
        "definition": "Customer in the Priority segment with elevated service and relationship expectations.",
        "synonyms": ["nasabah prioritas", "pelanggan prioritas", "priority segment"],
        "related_dimension_keys": ["segment"],
    },
    {
        "key": "failed_transaction",
        "term": "Failed Transaction",
        "definition": "A transaction attempt recorded with status Failed (not completed successfully).",
        "synonyms": ["transaksi gagal", "gagal transaksi", "failed tx"],
        "related_metric_keys": ["failed_transaction_rate"],
    },
    {
        "key": "high_risk",
        "term": "High Risk",
        "definition": "Customer classified in the High risk tier based on synthetic banking policy.",
        "synonyms": ["risiko tinggi", "high risk tier", "nasabah berisiko tinggi"],
        "related_dimension_keys": ["risk_tier"],
    },
    {
        "key": "transaction_attempt",
        "term": "Transaction Attempt",
        "definition": "Any row in the transactions table regardless of final status (includes Failed and Success).",
        "synonyms": ["percobaan transaksi", "attempt transaksi", "semua transaksi"],
        "related_metric_keys": ["transaction_count"],
    },
    {
        "key": "active_customer",
        "term": "Active Customer",
        "definition": "Customer whose customer_status is Active in the customers table.",
        "synonyms": ["nasabah aktif", "customer aktif", "pelanggan aktif"],
        "related_metric_keys": ["active_customers"],
        "related_dimension_keys": ["customer_status"],
    },
)

METRIC_SPECS = (
    {
        "key": "total_transaction_amount",
        "name": "Total Transaction Amount",
        "source_entity_key": ENTITY_TRANSACTIONS_KEY,
        "expression": "SUM(amount)",
        "aggregation": "sum",
        "business_definition": "Total monetary value of transactions in the selected scope.",
        "format": "currency",
        "synonyms": ["nominal transaksi", "total amount", "nilai transaksi", "jumlah nominal"],
    },
    {
        "key": "transaction_count",
        "name": "Transaction Count",
        "source_entity_key": ENTITY_TRANSACTIONS_KEY,
        "expression": "COUNT(transaction_id)",
        "aggregation": "count",
        "business_definition": "Number of transaction attempts in the selected scope.",
        "synonyms": ["jumlah transaksi", "banyak transaksi", "hitung transaksi", "transaction volume"],
    },
    {
        "key": "average_transaction_value",
        "name": "Average Transaction Value",
        "source_entity_key": ENTITY_TRANSACTIONS_KEY,
        "expression": "AVG(amount)",
        "aggregation": "avg",
        "business_definition": "Average amount per transaction in the selected scope.",
    },
    {
        "key": "active_customers",
        "name": "Active Customers",
        "source_entity_key": ENTITY_CUSTOMERS_KEY,
        "expression": "COUNT(DISTINCT CASE WHEN customer_status = 'Active' THEN customer_id END)",
        "aggregation": "count",
        "business_definition": "Distinct customers whose customer_status is Active.",
        "synonyms": ["nasabah aktif", "total customer aktif", "jumlah nasabah aktif", "active customer count"],
    },
    {
        "key": "failed_transaction_count",
        "name": "Failed Transaction Count",
        "source_entity_key": ENTITY_TRANSACTIONS_KEY,
        "expression": "SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END)",
        "aggregation": "count",
        "business_definition": "Count of transaction attempts with status Failed.",
    },
    {
        "key": "successful_transaction_count",
        "name": "Successful Transaction Count",
        "source_entity_key": ENTITY_TRANSACTIONS_KEY,
        "expression": "SUM(CASE WHEN status = 'Success' THEN 1 ELSE 0 END)",
        "aggregation": "count",
        "business_definition": "Count of transaction attempts with status Success.",
    },
    {
        "key": "failed_transaction_rate",
        "name": "Failed Transaction Rate",
        "source_entity_key": ENTITY_TRANSACTIONS_KEY,
        "expression": "AVG(CASE WHEN status = 'Failed' THEN 1.0 ELSE 0.0 END)",
        "aggregation": "avg",
        "format": "percent",
        "business_definition": (
            "Failed transaction attempts divided by total transaction attempts "
            "(aligned with Retail Banking Knowledge policy)."
        ),
    },
)

EXTRA_DIMENSIONS = (
    {
        "key": "transaction_month",
        "name": "Transaction Month",
        "source_entity_key": ENTITY_TRANSACTIONS_KEY,
        "source_column": "transaction_date",
        "data_type": "date",
        "description": "Calendar month derived from transaction_date.",
        "metadata": {"time_grain": "month"},
    },
)

RELATIONSHIP_SPEC = {
    "key": "transactions_to_customers",
    "name": "Transactions to Customers",
    "from_entity_key": ENTITY_TRANSACTIONS_KEY,
    "to_entity_key": ENTITY_CUSTOMERS_KEY,
    "relationship_type": "many_to_one",
    "join_type": "inner",
    "join_expression": "a.customer_id = b.customer_id",
    "description": "Many transactions belong to one customer.",
}
