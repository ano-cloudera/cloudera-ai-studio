#!/usr/bin/env python3
"""Write the two sample Knowledge PDFs (one section per page, so answers can cite a page).

Usage (backend venv): python samples/fulfillment/make_policy_pdf.py
Output in samples/fulfillment/knowledge/ (kept out of git; upload both to one Knowledge library):
  Delivery_Returns_Policy.pdf   service levels, carrier review, late deliveries, returns, fulfillment targets
  Carrier_Operations_Guide.pdf  carrier contracts, regional coverage, claims, escalation, peak season
The thresholds match the sample data and the MCP model.
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUT_DIR = Path(__file__).resolve().parent / "knowledge"

POLICY = [
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


GUIDE = [
    ("1. Carrier contracts", [
        "The company works with three carriers: NusaCargo, KilatKirim and FastExpress.",
        "NusaCargo is the lowest cost carrier and is used for regular delivery on long routes. KilatKirim is the default carrier for express delivery. FastExpress is used for time-critical parcels in dense cities.",
        "Each contract is renewed every 12 months. Renewal is based on the late delivery rate of the last two quarters, not on price alone.",
    ]),
    ("2. Regional coverage", [
        "Java regions (DKI Jakarta, Jawa Barat, Jawa Tengah, Jawa Timur) are served by all three carriers.",
        "Outside Java (Sumatera Utara, Kalimantan Timur, Sulawesi Selatan, Bali) the default is NusaCargo, with KilatKirim as backup for express orders.",
        "Kalimantan Timur has the longest transit time because parcels are consolidated at a hub before the final leg, so orders there should be shipped as early as possible in the day.",
    ]),
    ("3. Damaged and lost parcels", [
        "A parcel is declared lost when it has had no tracking update for 7 days. The customer is refunded in full and a claim is filed with the carrier.",
        "Damage must be reported by the customer within 48 hours of delivery with photos. The carrier pays up to IDR 2,000,000 per parcel for insured shipments.",
        "Parcels with a declared value above IDR 5,000,000 must be insured. Insurance costs 0.5 percent of the declared value.",
    ]),
    ("4. Escalation", [
        "If a carrier late delivery rate stays above 15 percent for two months in a row, the logistics manager opens a recovery plan with the carrier.",
        "Recovery plans last 60 days. If the late delivery rate is not below 12 percent at the end, the volume of that carrier in the region is reduced by half.",
        "Customer complaints about delivery are answered within 4 working hours.",
    ]),
    ("5. Peak season", [
        "Peak season runs from 20 November to 5 January. Service levels are extended by 2 days: 6 days for regular delivery and 4 days for express delivery.",
        "During peak season the late delivery voucher is not paid for shipments delivered within the extended service level.",
        "The warehouse adds a second shift and pick and pack stays within 24 hours of payment.",
    ]),
]


def write(name: str, heading: str, sections: list[tuple[str, list[str]]]) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for title, paragraphs in sections:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 12, heading, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)
        for text in paragraphs:
            pdf.multi_cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
    out = OUT_DIR / name
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    print(f"wrote {out} ({len(sections)} pages)")


def main() -> None:
    write("Delivery_Returns_Policy.pdf", "Delivery and Returns Policy (sample)", POLICY)
    write("Carrier_Operations_Guide.pdf", "Carrier Operations Guide (sample)", GUIDE)


if __name__ == "__main__":
    main()
