#!/usr/bin/env python3
"""Create, validate and publish the Customer 360 semantic model through the Backend API (stdlib only).

Run it in a Session terminal of the Cloudera AI project, after the Customer 360 tables are in Trino and the Trino Data Source exists:

    python3 samples/customer360/build_semantic_model.py            # create a new version, validate, publish to Ask Data
    python3 samples/customer360/build_semantic_model.py --dry-run  # print what it would create, call nothing
    python3 samples/customer360/build_semantic_model.py --no-publish

The Backend URL (with its secret path) is derived the way the deploy Job does it; pass --base-url to use another one.
Running it again is safe: the model is found by its key and every run adds a new version, so a published version is never edited.
Nothing secret is printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))

MODEL_KEY = "customer_360"
MODEL_NAME = "Customer 360"
MODEL_DESCRIPTION = "One view of the customer: who they are, what they buy, how often they complain, which campaigns reach them and whether they leave."
CATALOG, SCHEMA = "iceberg", "default"

# Each entity is one Trino table or view. A dimension key is unique in a model, so the dimensions that exist in several tables
# carry a prefix in the key (txn_channel, touch_channel); the name and synonyms are what people type.
ENTITIES = [
    {"key": "customer_360", "name": "Customer 360", "table": "v_customer_360", "kind": "view", "primary_key": "customer_id",
     "description": "One row per customer with spend, orders, tickets, campaign conversions, last NPS and an RFM segment. Use it for any question about customers by region, tier, segment or acquisition channel."},
    {"key": "transactions", "name": "Transactions", "table": "c360_transactions", "kind": "table", "primary_key": "transaction_id",
     "description": "One row per purchase. Use it for revenue, orders and discounts over time, by product category, sales channel or payment method."},
    {"key": "support_tickets", "name": "Support tickets", "table": "c360_support_tickets", "kind": "table", "primary_key": "ticket_id",
     "description": "One row per support ticket with category, priority, resolution time and the customer's satisfaction score."},
    {"key": "campaign_touches", "name": "Campaign touches", "table": "c360_campaign_touches", "kind": "table", "primary_key": "touch_id",
     "description": "One row per marketing message or ad sent to a customer and how far it got: sent, opened, clicked or converted."},
    {"key": "nps_surveys", "name": "NPS surveys", "table": "c360_nps_surveys", "kind": "table", "primary_key": "survey_id",
     "description": "One row per Net Promoter Score survey answer with its main comment theme."},
]

# (key, name, entity, column, data type, synonyms)
DIMENSIONS = [
    ("region_name", "Region", "customer_360", "region_name", "String", ["wilayah", "provinsi", "daerah", "province"]),
    ("age_band", "Age Band", "customer_360", "age_band", "String", ["age group", "usia", "kelompok usia"]),
    ("gender", "Gender", "customer_360", "gender", "String", ["jenis kelamin"]),
    ("acquisition_channel", "Acquisition Channel", "customer_360", "acquisition_channel", "String", ["how customers joined", "sumber pelanggan", "channel akuisisi"]),
    ("loyalty_tier", "Loyalty Tier", "customer_360", "loyalty_tier", "String", ["tier", "level loyalti", "membership tier"]),
    ("rfm_segment", "Customer Segment", "customer_360", "rfm_segment", "String", ["segment", "segmen", "segmen pelanggan", "rfm"]),
    ("signup_date", "Signup Date", "customer_360", "signup_date", "Date", ["join date", "tanggal daftar"]),
    ("txn_date", "Transaction Date", "transactions", "txn_date", "Date", ["order date", "purchase date", "tanggal transaksi", "month", "bulan"]),
    ("product_category", "Product Category", "transactions", "product_category", "String", ["category", "kategori produk", "kategori"]),
    ("txn_channel", "Sales Channel", "transactions", "channel", "String", ["sales channel", "channel penjualan", "purchase channel"]),
    ("payment_method", "Payment Method", "transactions", "payment_method", "String", ["metode pembayaran", "payment"]),
    ("opened_date", "Ticket Date", "support_tickets", "opened_date", "Date", ["ticket opened date", "tanggal tiket", "month", "bulan"]),
    ("ticket_category", "Ticket Category", "support_tickets", "category", "String", ["complaint type", "jenis keluhan", "kategori tiket"]),
    ("ticket_priority", "Ticket Priority", "support_tickets", "priority", "String", ["prioritas"]),
    ("ticket_status", "Ticket Status", "support_tickets", "status", "String", ["status tiket"]),
    ("touch_date", "Campaign Date", "campaign_touches", "touch_date", "Date", ["tanggal kampanye", "month", "bulan"]),
    ("campaign", "Campaign", "campaign_touches", "campaign", "String", ["campaign name", "kampanye", "promo"]),
    ("touch_channel", "Marketing Channel", "campaign_touches", "channel", "String", ["channel marketing", "email push whatsapp ads", "marketing channel"]),
    ("touch_outcome", "Campaign Outcome", "campaign_touches", "outcome", "String", ["hasil kampanye", "funnel stage"]),
    ("survey_date", "Survey Date", "nps_surveys", "survey_date", "Date", ["tanggal survei", "month", "bulan"]),
    ("comment_theme", "Survey Theme", "nps_surveys", "comment_theme", "String", ["comment theme", "tema komentar", "alasan nps"]),
]

# (key, name, entity, expression, unit, synonyms, business definition)
METRICS = [
    ("total_customers", "Total Customers", "customer_360", "COUNT(customer_id)", "customers", ["number of customers", "customer count", "jumlah pelanggan", "total pelanggan"],
     "The number of customers in the base."),
    ("churned_customers", "Churned Customers", "customer_360", "COUNT(CASE WHEN NOT is_active THEN 1 END)", "customers", ["lost customers", "pelanggan churn", "pelanggan yang pergi"],
     "Customers who stopped buying and were closed as churned."),
    ("churn_rate", "Churn Rate (%)", "customer_360", "COUNT(CASE WHEN NOT is_active THEN 1 END) * 100.0 / COUNT(customer_id)", "percent", ["churn", "attrition rate", "customer attrition", "tingkat churn"],
     "Churned customers as a share of all customers."),
    ("at_risk_customers", "At-risk Customers", "customer_360", "COUNT(CASE WHEN rfm_segment = 'At Risk' THEN 1 END)", "customers", ["customers at risk", "pelanggan berisiko", "hampir churn"],
     "Active customers whose last purchase was 91 to 180 days before the end of the data."),
    ("customer_revenue", "Customer Revenue (IDR)", "customer_360", "SUM(total_spend)", "IDR", ["revenue by region", "revenue by tier", "revenue by segment", "spend by segment", "pendapatan per wilayah", "pendapatan per tier"],
     "Total net spend of the customers in the group. Use it to split revenue by region, tier or segment."),
    ("customer_lifetime_value", "Customer Lifetime Value (IDR)", "customer_360", "AVG(total_spend)", "IDR", ["CLV", "LTV", "lifetime value", "nilai pelanggan", "rata-rata belanja pelanggan"],
     "Average total net spend per customer over the whole data period."),
    ("average_orders_per_customer", "Average Orders per Customer", "customer_360", "AVG(txn_count)", "orders", ["orders per customer", "purchase frequency", "frekuensi belanja"],
     "Average number of purchases per customer."),
    ("repeat_delivery_complainers", "Customers with Repeat Delivery Complaints", "customer_360", "COUNT(CASE WHEN delivery_ticket_count >= 2 THEN 1 END)", "customers",
     ["repeat delivery complaints", "keluhan pengiriman berulang"], "Customers who opened two or more Delivery tickets."),
    ("repeat_delivery_churn_rate", "Churn Rate of Repeat Delivery Complainers (%)", "customer_360",
     "COUNT(CASE WHEN delivery_ticket_count >= 2 AND NOT is_active THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN delivery_ticket_count >= 2 THEN 1 END), 0)", "percent",
     ["churn of customers with delivery complaints"], "Churn rate among customers with two or more Delivery tickets."),
    ("no_delivery_issue_churn_rate", "Churn Rate of Customers without Delivery Complaints (%)", "customer_360",
     "COUNT(CASE WHEN delivery_ticket_count < 2 AND NOT is_active THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN delivery_ticket_count < 2 THEN 1 END), 0)", "percent",
     ["churn of customers without delivery complaints"], "Churn rate among customers with fewer than two Delivery tickets."),
    ("total_revenue", "Total Revenue (IDR)", "transactions", "SUM(amount)", "IDR", ["revenue", "sales", "net sales", "omzet", "pendapatan", "penjualan"],
     "Net amount paid, after discounts."),
    ("total_transactions", "Total Transactions", "transactions", "COUNT(transaction_id)", "orders", ["number of orders", "order count", "jumlah transaksi", "jumlah order"],
     "The number of purchases."),
    ("average_order_value", "Average Order Value (IDR)", "transactions", "AVG(amount)", "IDR", ["AOV", "basket size", "rata-rata nilai order", "nilai order rata-rata"],
     "Average net amount per purchase."),
    ("total_discount", "Total Discount (IDR)", "transactions", "SUM(discount_amount)", "IDR", ["discounts given", "total diskon"], "Discount given on purchases."),
    ("discount_rate", "Discount Rate (%)", "transactions", "SUM(discount_amount) * 100.0 / NULLIF(SUM(amount) + SUM(discount_amount), 0)", "percent", ["discount share", "persentase diskon"],
     "Discount as a share of the amount before discount."),
    ("total_tickets", "Total Tickets", "support_tickets", "COUNT(ticket_id)", "tickets", ["number of tickets", "ticket volume", "jumlah tiket", "keluhan"], "The number of support tickets."),
    ("average_resolution_hours", "Average Resolution Hours", "support_tickets", "AVG(resolution_hours)", "hours", ["resolution time", "time to resolve", "waktu penyelesaian"],
     "Average hours from opening to resolution, for resolved tickets."),
    ("average_csat", "Average CSAT", "support_tickets", "AVG(csat_score)", "score", ["csat", "customer satisfaction", "kepuasan pelanggan"],
     "Average satisfaction score from 1 to 5, for tickets that were rated."),
    ("delivery_ticket_share", "Delivery Ticket Share (%)", "support_tickets", "COUNT(CASE WHEN category = 'Delivery' THEN 1 END) * 100.0 / COUNT(ticket_id)", "percent",
     ["share of delivery tickets", "porsi keluhan pengiriman"], "Delivery tickets as a share of all tickets."),
    ("total_touches", "Total Campaign Touches", "campaign_touches", "COUNT(touch_id)", "touches", ["messages sent", "campaign volume", "jumlah pesan kampanye"], "The number of marketing messages and ads sent."),
    ("converted_touches", "Converted Touches", "campaign_touches", "COUNT(CASE WHEN outcome = 'Converted' THEN 1 END)", "touches", ["conversions", "jumlah konversi"], "Touches that ended in a purchase."),
    ("campaign_conversion_rate", "Campaign Conversion Rate (%)", "campaign_touches", "COUNT(CASE WHEN outcome = 'Converted' THEN 1 END) * 100.0 / COUNT(touch_id)", "percent",
     ["conversion rate", "marketing conversion", "tingkat konversi"], "Converted touches as a share of all touches."),
    ("campaign_click_rate", "Campaign Click Rate (%)", "campaign_touches", "COUNT(CASE WHEN outcome IN ('Clicked', 'Converted') THEN 1 END) * 100.0 / COUNT(touch_id)", "percent",
     ["click rate", "click through rate", "CTR"], "Touches that were clicked or converted, as a share of all touches."),
    ("campaign_cost", "Campaign Cost (IDR)", "campaign_touches", "SUM(cost)", "IDR", ["marketing cost", "marketing spend", "biaya kampanye"], "Cost of the touches."),
    ("cost_per_conversion", "Cost per Conversion (IDR)", "campaign_touches", "SUM(cost) / NULLIF(COUNT(CASE WHEN outcome = 'Converted' THEN 1 END), 0)", "IDR",
     ["cost per acquisition", "CPA", "biaya per konversi"], "Campaign cost divided by the number of conversions."),
    ("net_promoter_score", "Net Promoter Score", "nps_surveys",
     "(COUNT(CASE WHEN nps_score >= 9 THEN 1 END) - COUNT(CASE WHEN nps_score <= 6 THEN 1 END)) * 100.0 / COUNT(survey_id)", "score", ["NPS", "net promoter"],
     "Promoters (9 to 10) minus detractors (0 to 6) as a percentage of all answers."),
    ("survey_responses", "Survey Responses", "nps_surveys", "COUNT(survey_id)", "answers", ["number of survey answers", "jumlah responden", "jumlah jawaban survei"], "The number of NPS answers."),
]

# (key, term, definition, related metric keys)
TERMS = [
    ("churn", "Churn", "A customer who stopped buying and was closed in the data. Churn Rate is their share of all customers.", ["churn_rate", "churned_customers"]),
    ("rfm", "RFM segment", "A customer segment from recency of the last purchase and loyalty tier: Champions, Loyal, At Risk, Hibernating, New or Churned.", ["at_risk_customers"]),
    ("clv", "Customer lifetime value", "Average net spend per customer over the data period (not a forecast).", ["customer_lifetime_value"]),
    ("nps", "Net Promoter Score", "Promoters (9-10) minus detractors (0-6), as a percentage of answers. Passives (7-8) count in the total only.", ["net_promoter_score"]),
]


class ApiError(RuntimeError):
    pass


def entity_payload(entity: dict, connector_id: str) -> dict:
    return {
        "key": entity["key"], "name": entity["name"], "description": entity["description"], "source_type": "trino",
        "catalog": CATALOG, "db_schema": SCHEMA, "table_name": entity["table"] if entity["kind"] == "table" else None,
        "view_name": entity["table"] if entity["kind"] == "view" else None, "primary_key": entity["primary_key"], "connection_id": connector_id,
    }


def dimension_payload(row: tuple) -> dict:
    key, name, entity, column, data_type, synonyms = row
    return {"key": key, "name": name, "source_entity_key": entity, "source_column": column, "data_type": data_type, "synonyms": synonyms}


def metric_payload(row: tuple, dimension_keys: dict[str, list[str]]) -> dict:
    key, name, entity, expression, unit, synonyms, definition = row
    return {
        "key": key, "name": name, "expression": expression, "source_entity_key": entity, "description": definition,
        "business_definition": definition, "unit": unit, "synonyms": synonyms, "allowed_dimension_keys": dimension_keys[entity],
    }


def term_payload(row: tuple) -> dict:
    key, term, definition, metric_keys = row
    return {"key": key, "term": term, "definition": definition, "synonyms": [], "related_metric_keys": metric_keys}


def dimension_keys_by_entity() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {e["key"]: [] for e in ENTITIES}
    for row in DIMENSIONS:
        out[row[2]].append(row[0])
    return out


def plan(connector_id: str) -> dict[str, list[dict]]:
    keys = dimension_keys_by_entity()
    return {
        "entities": [entity_payload(e, connector_id) for e in ENTITIES],
        "dimensions": [dimension_payload(r) for r in DIMENSIONS],
        "metrics": [metric_payload(r, keys) for r in METRICS],
        "terms": [term_payload(r) for r in TERMS],
    }


class Api:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")

    def call(self, method: str, path: str, body: dict | None = None, *, ok_statuses: tuple[int, ...] = (200,)) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(f"{self.base}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310 - the Backend URL the operator passes
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode(errors="replace")[:1500]
            if exc.code in ok_statuses:
                return json.loads(text) if text.startswith("{") else {"detail": text}
            raise ApiError(f"{method} {path} -> HTTP {exc.code}: {text}") from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"{method} {path} -> {exc.reason}") from exc


def pick_connector(api: Api, wanted: str | None) -> dict:
    connectors = api.call("GET", "/api/v1/connectors?connector_type=trino")["connectors"]
    if wanted:
        connectors = [c for c in connectors if c["id"] == wanted]
    if len(connectors) != 1:
        names = ", ".join(f"{c.get('name')} ({c['id']})" for c in connectors) or "none"
        raise ApiError(f"Expected exactly one Trino Data Source, found {len(connectors)}: {names}. Create it in Data Sources first, or pass --connector-id.")
    return connectors[0]


def new_draft(api: Api) -> tuple[str, str]:
    """The model (created when missing) and a fresh DRAFT version of it."""
    models = api.call("GET", "/api/v1/semantic/models")["models"]
    model = next((m for m in models if m["key"] == MODEL_KEY), None)
    if model is None:
        model = api.call("POST", "/api/v1/semantic/models", {"name": MODEL_NAME, "key": MODEL_KEY, "description": MODEL_DESCRIPTION})["model"]
        versions = api.call("GET", f"/api/v1/semantic/models/{model['id']}/versions")["versions"]
        return model["id"], max(versions, key=lambda v: v["version_number"])["id"]
    version = api.call("POST", f"/api/v1/semantic/models/{model['id']}/versions")["version"]
    return model["id"], version["id"]


def default_base_url() -> str | None:
    import judge_answers  # noqa: PLC0415 - owns the Backend URL derivation inside Cloudera AI

    return judge_answers.default_base_url(dict(os.environ))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url")
    parser.add_argument("--connector-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args(argv)

    if args.dry_run:
        body = plan("<trino data source id>")
        print(f"Model {MODEL_KEY}: " + ", ".join(f"{len(v)} {k}" for k, v in body.items()))
        for metric in body["metrics"]:
            print(f"  [{metric['source_entity_key']}] {metric['name']}")
        return 0

    base_url = args.base_url or default_base_url()
    if not base_url:
        print("No Backend URL: run this in a Cloudera AI Session, or pass --base-url (with its secret path).", file=sys.stderr)
        return 2
    api = Api(base_url)
    try:
        connector = pick_connector(api, args.connector_id)
        print(f"Trino Data Source: {connector.get('name')}")
        model_id, version_id = new_draft(api)
        print(f"Model {MODEL_KEY}, new draft version {version_id}")
        body = plan(connector["id"])
        for kind, singular in (("entities", "entities"), ("dimensions", "dimensions"), ("metrics", "metrics"), ("terms", "terms")):
            for item in body[kind]:
                api.call("POST", f"/api/v1/semantic/versions/{version_id}/{singular}", item)
            print(f"  created {len(body[kind])} {kind}")
        report = api.call("POST", f"/api/v1/semantic/versions/{version_id}/validate", {"mode": "full"})
        print("Validation:", json.dumps(report, default=str)[:1200])
        readiness = api.call("GET", f"/api/v1/semantic/versions/{version_id}/readiness")
        print("Readiness:", json.dumps(readiness, default=str)[:600])
        if args.no_publish:
            print("Not published (--no-publish). Review the draft in Semantic Layer.")
            return 0
        result = api.call("POST", f"/api/v1/semantic/models/{model_id}/publish-to-ask-data", {"version_id": version_id}, ok_statuses=(200, 422, 502))
        print("Publish:", json.dumps(result, default=str)[:1200])
        status = str(result.get("status", "")).lower()
        return 0 if status not in {"needs_attention", "activation_failed"} and "detail" not in result else 1
    except ApiError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
