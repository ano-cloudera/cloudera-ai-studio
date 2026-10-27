#!/usr/bin/env python3
"""Live API gates for SEMANTIC_LAYER_V2 Phase 2A closure (delegates to Phase 2 gate)."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    script = Path(__file__).resolve().parent / "sem_p2_live_gate.py"
    ns = runpy.run_path(str(script))
    raise SystemExit(ns["main"]())
