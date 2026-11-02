#!/usr/bin/env python3
"""Write the sample delivery and returns policy as a PDF (one section per page, so answers can cite a page).

Usage (backend venv): python samples/fulfillment/make_policy_pdf.py
Output: samples/fulfillment/knowledge/Delivery_Returns_Policy.pdf (kept out of git; upload it to a Knowledge library).
The thresholds match the sample data and the MCP model.
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent / "knowledge" / "Delivery_Returns_Policy.pdf"

SECTIONS = [
    ("1. Delivery service levels", [
        "Regular delivery has a service level of 4 days. Express delivery has a service level of 2 days.",
        "The days are counted from the ship date to the delivered date.",
        "A shipment is late when it is delivered after its service level.",
    ]),
    ("2. Carrier performance review", [
        "The late delivery rate is reviewed per carrier and region for each calendar month.",
        "When a carrier's late delivery rate in a region is above 15 percent, a carrier performance review is triggered.",
        "When it is above 25 percent, new volume to that carrier in that region is held until a recovery plan is agreed.",
        "A rate gap between regions alone is not a reason to change carriers: check the carrier mix of the region first.",
    ]),
    ("3. Late and failed deliveries", [
        "When a shipment arrives more than 2 days after its service level, the customer receives a voucher of 10 percent of the order value, up to IDR 50,000.",
        "A failed delivery is attempted again within 24 hours. After 2 failed attempts the parcel returns to the warehouse and the customer is contacted.",
    ]),
    ("4. Returns and refunds", [
        "Customers can return an item within 7 days after delivery. Electronics with a defect can be returned within 14 days.",
        "Opened beauty products are not returnable for hygiene reasons.",
        "Refunds are paid within 5 working days after the warehouse receives the item.",
    ]),
    ("5. Fulfillment targets", [
        "Orders are picked and packed within 24 hours of payment. Marketplace orders have a target of 36 hours because of batch handover.",
        "An order not shipped within 24 hours of payment (36 hours for marketplace) is escalated to the warehouse lead.",
        "Cancelled orders are not shipped and are not counted in delivery metrics.",
    ]),
]


def main() -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for title, paragraphs in SECTIONS:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 12, "Delivery and Returns Policy (sample)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)
        for text in paragraphs:
            pdf.multi_cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    print(f"wrote {OUT} ({len(SECTIONS)} pages)")


if __name__ == "__main__":
    main()
