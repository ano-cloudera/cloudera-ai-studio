#!/usr/bin/env python3
"""Regenerate Golden Banking Knowledge PDFs from markdown sources (deterministic content)."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "demo" / "knowledge"
OUT = SRC / "generated"

PDF_SPECS = (
    ("transaction-policy.md", "Retail Banking Transaction Policy.pdf"),
    ("customer-segment-risk-guide.md", "Customer Segment and Risk Guide.pdf"),
)


def _render_markdown_to_pdf(md_text: str, *, title: str) -> bytes:
    from fpdf import FPDF

    class DemoPDF(FPDF):
        def footer(self) -> None:
            self.set_y(-12)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(100, 100, 100)
            self.cell(0, 8, f"Golden Demo - Page {self.page_no()}", align="C")

    pdf = DemoPDF()
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_creator("Cloudera AI Studio Golden Banking Demo")
    pdf.set_author("Synthetic Demo Content")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)

    def _cell(text: str, *, h: float = 5) -> None:
        pdf.set_x(pdf.l_margin)
        safe = (
            text.replace("\u2014", "-")
            .replace("\u2013", "-")
            .replace("\u2022", "-")
            .encode("latin-1", "replace")
            .decode("latin-1")
        )
        pdf.multi_cell(pdf.epw, h, safe)

    _cell(title, h=9)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 11)

    for raw_line in md_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            pdf.ln(3)
            continue
        if line.startswith("**") and line.endswith("**"):
            _cell(line.strip("*"))
            continue
        if line.startswith("# "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 14)
            _cell(line[2:].strip(), h=7)
            pdf.set_font("Helvetica", "", 11)
            continue
        if line.startswith("## "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 12)
            _cell(line[3:].strip(), h=6)
            pdf.set_font("Helvetica", "", 11)
            continue
        if line.startswith("### "):
            pdf.ln(1)
            pdf.set_font("Helvetica", "B", 11)
            _cell(line[4:].strip(), h=6)
            pdf.set_font("Helvetica", "", 11)
            continue
        if line.startswith("|"):
            if re.match(r"^\|\s*-+", line):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            row = " | ".join(c for c in cells if c)
            if not row:
                continue
            pdf.set_font("Helvetica", "", 10)
            _cell(row)
            pdf.set_font("Helvetica", "", 11)
            continue
        if line.startswith("- **"):
            m = re.match(r"- \*\*(.+?)\*\*:?\s*(.*)", line)
            if m:
                _cell(f"- {m.group(1)}: {m.group(2) or ''}".strip())
                continue
        if line.startswith("- "):
            _cell(f"- {line[2:].strip()}")
            continue
        # Strip lightweight markdown emphasis
        plain = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        plain = plain.replace("—", "-")
        if plain.strip():
            _cell(plain)

    out = pdf.output()
    if isinstance(out, bytearray):
        return bytes(out)
    if isinstance(out, bytes):
        return out
    return str(out).encode("latin-1")


def main() -> int:
    try:
        import fpdf  # noqa: F401
    except ImportError:
        print("Install fpdf2: pip install fpdf2", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for md_name, pdf_name in PDF_SPECS:
        md_path = SRC / md_name
        if not md_path.is_file():
            print(f"Missing source {md_path}", file=sys.stderr)
            return 1
        md_text = md_path.read_text(encoding="utf-8")
        title = md_text.splitlines()[0].lstrip("# ").strip()
        pdf_bytes = _render_markdown_to_pdf(md_text, title=title)
        out_path = OUT / pdf_name
        out_path.write_bytes(pdf_bytes)
        digest = hashlib.sha256(pdf_bytes).hexdigest()
        manifest[pdf_name] = digest
        print(f"Wrote {out_path} sha256={digest[:16]}…")

    # Text extract sanity (same parser as ingestion)
    from pypdf import PdfReader
    import io

    for _, pdf_name in PDF_SPECS:
        reader = PdfReader(io.BytesIO((OUT / pdf_name).read_bytes()))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        if len(text.strip()) < 200:
            print(f"PDF text too short: {pdf_name}", file=sys.stderr)
            return 1
        print(f"OK extract {pdf_name}: {len(text)} chars")

    meta_path = OUT / "manifest.sha256.json"
    import json

    meta_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
