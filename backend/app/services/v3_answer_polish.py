"""Clean tempo_agent_v3 prose when tabular data is already in `data.rows`."""

from __future__ import annotations

import re

from app.core.models import AnalysisOutput, AskDataResponse
from app.services.local_agent_client import markdown_to_plain_answer

_TABLE_LINE = re.compile(r"^\s*\|")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}")
_SECTION = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


def _strip_markdown_tables(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    skipping_table = False
    for line in lines:
        if _TABLE_LINE.match(line):
            skipping_table = True
            continue
        if skipping_table and (_TABLE_SEP.match(line) or _TABLE_LINE.match(line)):
            continue
        skipping_table = False
        kept.append(line)
    return "\n".join(kept).strip()


def _prose_only(text: str) -> str:
    cleaned = markdown_to_plain_answer(text)
    cleaned = _strip_markdown_tables(cleaned)
    cleaned = _SECTION.sub(r"\1:", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _split_insights(text: str) -> list[str]:
    insights: list[str] = []
    for block in re.split(r"\n(?=\d+\.\s)", text):
        line = block.strip()
        if not line:
            continue
        line = re.sub(r"^\d+\.\s*", "", line)
        if len(line) > 20:
            insights.append(line)
    return insights[:8]


def polish_v3_answer(response: AskDataResponse) -> AskDataResponse:
    if response.data.row_count <= 0:
        return response
    direct = _prose_only(response.answer.direct_answer)
    summary = _prose_only(response.answer.executive_summary)
    if summary == direct:
        summary = direct
    combined = f"{response.answer.direct_answer}\n{response.answer.executive_summary}"
    extra_insights = _split_insights(_prose_only(combined))
    insights = list(response.answer.insights)
    for item in extra_insights:
        if item not in insights:
            insights.append(item)
    if not direct and summary:
        direct = summary.split("\n")[0][:280]
    answer = response.answer.model_copy(
        update={
            "direct_answer": direct or "Berikut ringkasan berdasarkan data governed.",
            "executive_summary": summary or direct,
            "insights": insights[:8],
        }
    )
    return response.model_copy(update={"answer": answer})
