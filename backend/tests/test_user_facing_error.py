from __future__ import annotations

import asyncio

from app.services.user_facing_error import explain_failure


def test_a_failure_names_its_kind_and_code_but_nothing_from_the_driver() -> None:
    failure = {"kind": "internal", "code": "UNEXPECTED", "detail": "Column 'secret_col' cannot be resolved"}
    en = asyncio.run(explain_failure(provider=None, question="How many orders?", failure=failure, request_id="r1"))
    assert en.caveats[-1] == "Technical reason: internal/UNEXPECTED."
    assert not any("secret_col" in c for c in en.caveats)
    id_ = asyncio.run(explain_failure(provider=None, question="Berapa total orders bulan ini?", failure=failure, request_id="r2"))
    assert id_.caveats[-1] == "Rincian teknis: internal/UNEXPECTED."
