from __future__ import annotations

import pytest

from app.llm.base import ProviderError
from app.services.user_facing_error import explain_failure


class FailingProvider:
    async def generate_structured(self, *_args, **_kwargs):
        raise ProviderError("PROVIDER_ERROR")


@pytest.mark.asyncio
async def test_explain_failure_falls_back_for_impala_auth_without_llm() -> None:
    answer = await explain_failure(
        provider=FailingProvider(),
        question="Berapa fill rate?",
        failure={"kind": "data_backend", "code": "IMPALA_AUTH_FAILED"},
        request_id="req-1",
    )

    assert "impala" in answer.direct_answer.casefold() or "autentikasi" in answer.direct_answer.casefold()
    assert any("req-1" in caveat for caveat in answer.caveats)
    assert "Internal" not in answer.direct_answer


@pytest.mark.asyncio
async def test_explain_failure_sql_validation_fallback_is_user_friendly() -> None:
    answer = await explain_failure(
        provider=None,
        question="Gabungkan picking dan unloading",
        failure={"kind": "sql_validation", "code": "INVALID_SQL", "detail": "Column not allowed: x"},
        request_id="req-2",
    )

    assert "governed" in answer.executive_summary.casefold() or "sql" in answer.direct_answer.casefold()
    assert "Column not allowed" not in answer.direct_answer
