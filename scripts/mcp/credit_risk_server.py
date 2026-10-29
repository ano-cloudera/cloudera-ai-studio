#!/usr/bin/env python3
"""MCP server (stdio) exposing the demo credit-approval likelihood model.

Register it in Settings -> MCP connections as a stdio server:
    command: <python of the backend venv>     args: scripts/mcp/credit_risk_server.py

Works with mcp 1.x (FastMCP) and 2.x (MCPServer). Scoring is plain Python over credit_risk_model.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from credit_risk_scoring import assess  # noqa: E402

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except ImportError:  # mcp 2.x renamed it
    from mcp.server.mcpserver import MCPServer as _Server

server = _Server("Credit Risk Model")


@server.tool()
def assess_application_risk(
    credit_score: int,
    dti_ratio: float,
    requested_amount: float | None = None,
    application_channel: str | None = None,
    region_name: str | None = None,
    customer_segment: str | None = None,
    product_category: str | None = None,
) -> str:
    """Estimate the approval likelihood of a (synthetic) credit application and check it against the policy.

    credit_score: bureau-style score, 300-850. dti_ratio: debt-to-income as a fraction (0.40 means 40 percent).
    requested_amount: requested loan amount in IDR as a plain number (150 million is 150000000).
    application_channel: Digital, Branch or Partner. region_name: Bali, DKI Jakarta, Jawa Barat, Jawa Tengah,
    Jawa Timur or Sumatera Utara. customer_segment: Retail, SME or Priority.
    product_category: Personal Loan, Working Capital or Micro Loan.
    Returns the likelihood, the policy check (score >= 650 and DTI <= 0.45), the main drivers and the model details.
    This is an advisory indicator only: it never approves or rejects an application.
    """
    try:
        result = assess(
            credit_score,
            dti_ratio,
            requested_amount,
            application_channel,
            region_name,
            customer_segment,
            product_category,
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    server.run(transport="stdio")
