#!/usr/bin/env python3
"""MCP server (stdio) exposing a small, advisory late-delivery risk model for the fulfillment sample.

Register it in Settings -> MCP connections as a stdio server:
    command: <python of the backend venv>     args: samples/fulfillment/late_delivery_server.py
The estimate uses the same rules the synthetic data was generated with, so it is a demonstration, not a real forecast.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_data import CARRIERS, CATEGORIES, REGIONS, SLA, late_probability  # noqa: E402

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except ImportError:  # mcp 2.x renamed it
    from mcp.server.mcpserver import MCPServer as _Server

server = _Server("Late Delivery Risk")
REVIEW_THRESHOLD, SUSPEND_THRESHOLD = 0.15, 0.25  # the delivery policy: carrier review above 15%, volume hold above 25%


def _band(p: float) -> str:
    return "Low" if p < 0.10 else "Medium" if p < 0.20 else "High"


@server.tool()
def assess_delivery_risk(
    region_name: str,
    carrier: str,
    service_level: str = "Regular",
    product_category: str = "Fashion",
    ship_month: int | None = None,
) -> str:
    """Estimate how likely a shipment is to arrive after its SLA and check it against the delivery policy.

    region_name: Jabodetabek, Jawa Barat, Jawa Tengah, Jawa Timur, Sumatera, Kalimantan, Sulawesi or Bali-Nusa Tenggara.
    carrier: FastExpress, KilatKirim or NusaCargo. service_level: Regular (SLA 4 days) or Express (SLA 2 days).
    product_category: Electronics, Fashion, Home & Living, Beauty or Grocery. ship_month: 1-12 (optional).
    Returns the late probability, its band, the policy check and the main drivers.
    This is an advisory indicator only: it never reroutes, holds or cancels a shipment.
    """
    problems = []
    if region_name not in REGIONS:
        problems.append(f"region_name must be one of {', '.join(REGIONS)}")
    if carrier not in CARRIERS:
        problems.append(f"carrier must be one of {', '.join(CARRIERS)}")
    if service_level not in SLA:
        problems.append(f"service_level must be one of {', '.join(SLA)}")
    if product_category not in CATEGORIES:
        problems.append(f"product_category must be one of {', '.join(CATEGORIES)}")
    if problems:
        return json.dumps({"error": "; ".join(problems)})
    p = late_probability(region_name, carrier, service_level, ship_month or 1, product_category)
    drivers = []
    if region_name == "Kalimantan" and carrier == "NusaCargo":
        drivers.append("Kalimantan with NusaCargo has the highest late rate in the data")
    if region_name == "Sumatera" and carrier == "KilatKirim" and ship_month in (6, 7, 8):
        drivers.append("Sumatera with KilatKirim is late far more often from June to August")
    if product_category == "Home & Living":
        drivers.append("bulky goods (Home & Living) arrive late more often")
    if service_level == "Express":
        drivers.append("Express has a tighter SLA (2 days)")
    policy = "no action"
    if p > SUSPEND_THRESHOLD:
        policy = "above 25%: new volume to this carrier in this region is held pending a recovery plan"
    elif p > REVIEW_THRESHOLD:
        policy = "above 15%: carrier performance review is triggered"
    return json.dumps(
        {
            "late_probability": round(p, 3),
            "band": _band(p),
            "sla_days": SLA[service_level],
            "policy_check": policy,
            "drivers": drivers or ["no specific risk driver"],
            "note": "Advisory estimate on synthetic data. It never changes a shipment.",
        },
        indent=2,
    )


if __name__ == "__main__":
    server.run(transport="stdio")
