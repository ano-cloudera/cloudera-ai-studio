"""Shared constants for Golden Banking Knowledge demo (Phase 2)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LIBRARY_NAME = "Retail Banking Knowledge"
LIBRARY_DESCRIPTION = (
    "Business policies, customer segmentation guidance, and transaction definitions "
    "for the Golden Banking Demo."
)
LIBRARY_KEY = "golden_banking_knowledge"

PDF_DIR = ROOT / "demo" / "knowledge" / "generated"
PDF_TRANSACTION = PDF_DIR / "Retail Banking Transaction Policy.pdf"
PDF_SEGMENT = PDF_DIR / "Customer Segment and Risk Guide.pdf"

EVIDENCE_DIR = ROOT / "testing" / "evidence" / "golden-path" / "PHASE2-KNOWLEDGE"
