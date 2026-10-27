from __future__ import annotations

import random
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict


DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "random_queries.yaml"
Domain = Literal["sales", "b2b", "stock_tempo", "stock_sat_idm", "sat_oos", "cross_domain"]
Difficulty = Literal["simple", "medium", "complex"]


CURATED_CONTRACTS: dict[str, dict] = {
    "sales-001": {"metric": "gross_billing_value", "dimensions": []},
    "sales-002": {"metric": "gross_billing_value", "dimensions": ["calmonth"]},
    "sales-003": {"metric": "material_sell_in_value", "dimensions": ["material"]},
    "sales-004": {"metric": "customer_sell_in_value", "dimensions": ["customer"]},
    "sales-005": {"metric": "sales_office_material_sell_in_value", "dimensions": ["sales_office", "material"]},
    "b2b-001": {"metric": "b2b_branch_sell_out_value", "dimensions": ["calmonth"]},
    "b2b-002": {"metric": "b2b_branch_sell_out_value", "dimensions": ["branch"]},
    "b2b-003": {"metric": "b2b_branch_sell_out_quantity", "dimensions": ["e_store"]},
    "b2b-004": {"metric": "b2b_material_plu_value", "dimensions": ["material", "kode_plu"]},
    "b2b-005": {"metric": "b2b_customer_sell_out_quantity", "dimensions": ["customer", "branch"]},
    "stock-tempo-001": {"metric": "stock_tempo_total_qty", "dimensions": ["calmonth"]},
    "stock-tempo-002": {"metric": "material_warehouse_stock_quantity", "dimensions": ["material"]},
    "stock-tempo-003": {"metric": "stock_tempo_value", "dimensions": ["plant"]},
    "stock-tempo-004": {"metric": "stock_tempo_value", "dimensions": ["calmonth", "material"]},
    "stock-tempo-005": {"metric": "months_of_stock_cover", "dimensions": ["material"]},
    "stock-idm-001": {"metric": "sat_dc_stock_quantity", "dimensions": ["thn", "bln"]},
    "stock-idm-002": {"metric": "sat_dc_stock_quantity", "dimensions": ["dcname"]},
    "stock-idm-003": {"metric": "sat_dc_stock_value", "dimensions": ["plu"]},
    "stock-idm-004": {"metric": "sat_store_stock_quantity", "dimensions": ["division"]},
    "stock-idm-005": {"strategy": "sql_fallback", "metrics": ["sat_dc_stock_quantity", "sat_store_stock_quantity"]},
    "oos-001": {"metric": "sat_oos_rate", "dimensions": []},
    "oos-002": {"metric": "sat_oos_rate", "dimensions": ["calmonth_date"]},
    "oos-003": {"metric": "sat_oos_rate", "dimensions": ["material_code"]},
    "oos-004": {"metric": "sat_oos_rate", "dimensions": ["plu"]},
    "oos-005": {"metric": "sat_oos_rate", "dimensions": ["cust_id", "material_code"]},
    "cross-001": {"metric": "stock_tempo_to_sell_in_ratio", "dimensions": ["material"]},
    "cross-002": {"metric": "sell_out_to_sell_in_material_ratio_v2", "dimensions": ["material"]},
    "cross-003": {"metric": "branch_sell_out_vs_dc_stock", "dimensions": ["branch"]},
    "cross-004": {"metric": "sat_store_stock_vs_oos_rate", "dimensions": ["plu"]},
    "cross-005": {"metric": "sell_in_minus_sell_out_value", "dimensions": ["customer"]},
}


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    question: str
    domain: Domain
    domains: list[str]
    difficulty: Difficulty
    analysis_type: str
    expected_visualization: Literal["bar", "line", "area", "scatter", "pie", "table", "kpi"]


class QuestionBank:
    def __init__(self, path: Path = DATA_PATH) -> None:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        self._questions = [Question.model_validate(item) for item in payload["questions"]]

    def all(self) -> list[Question]:
        return list(self._questions)

    def query(
        self,
        *,
        domain: Domain | None = None,
        difficulty: Difficulty | None = None,
        limit: int = 1,
    ) -> list[Question]:
        matches = [
            item for item in self._questions
            if (domain is None or item.domain == domain)
            and (difficulty is None or item.difficulty == difficulty)
        ]
        count = min(max(limit, 1), 20, len(matches))
        return random.sample(matches, count) if count else []
