"""Multi-turn Ask Data, the way Cortex Analyst and Genie do it: every question is rewritten into one that stands on
its own, and the rest of the pipeline answers that question as if it were the first one.

The language model reads the new question next to the last few turns (what was asked, how it was read, which metric,
breakdown and filters were used, and the first rows of the answer) and writes the question out in full: "and per
carrier?" after "late rate in Jawa Timur in March 2026" becomes "late rate per carrier in Jawa Timur in March 2026".
A question that does not lean on the conversation passes through unchanged, so a fresh question can never inherit
the filters of an older one.

The same call tells small talk ("hi", "what can you do?") apart from a data question.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.llm.base import LLMProvider, ProviderError

logger = logging.getLogger(__name__)

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "conversation_rewrite.md"

_TURNS = 3
_ROWS = 5


class TurnReading(BaseModel):
    kind: Literal["data", "chat", "analysis"] = Field(
        default="data",
        description=(
            "chat = greeting, thanks or a question about what the assistant can do; analysis = a question one figure or "
            "one table cannot answer (why, what to do, an overview or summary, how two things relate); data = anything else."
        ),
    )
    uses_previous: bool = Field(
        default=False, description="True when the question leans on an earlier turn (a pronoun, an omitted metric, 'and per…')."
    )
    standalone_question: str = Field(
        default="", description="The question written out in full, in the user's language; the question itself when it already stands alone."
    )
    rationale: str = Field(default="", description="A few words on what was carried over.")

    # The fields below are what the rest of the pipeline used to read from the older turn reading; they keep
    # callers that still look at them working.
    @property
    def is_conversational(self) -> bool:
        return self.kind == "chat"

    @property
    def attach_domain_catalog(self) -> bool:
        return self.kind == "chat"

    @property
    def pipeline_question(self) -> str:
        return self.standalone_question


_SMALL_TALK = re.compile(
    r"^\s*(hi|hai|halo|hallo|hello|hey|pagi|siang|sore|malam|selamat (pagi|siang|sore|malam)|good (morning|afternoon|evening)|"
    r"thanks?|thank you|terima ?kasih|makasih|ok(e|ay)?|sip|mantap)\b[\s!.,?]*$",
    re.IGNORECASE,
)
_CAPABILITY = re.compile(
    r"\b(what can (you|i) (do|ask)|what else can|help me with|bisa (bantu )?apa( saja| aja| lagi)?|kamu bisa apa|"
    r"data apa (saja|aja)|bisa ditanyakan|apa yang bisa)\b",
    re.IGNORECASE,
)


def looks_like_small_talk(question: str) -> bool:
    """A greeting, a thank-you or a question about the assistant itself, recognised without the model."""
    text = question.strip()
    return bool(_SMALL_TALK.match(text) or _CAPABILITY.search(text))


def turn_memory(
    *,
    question: str,
    standalone_question: str | None,
    status: str,
    strategy: str,
    metric: str | None,
    dimensions: list[str] | None,
    scope: str | None,
    period: str | None = None,
) -> dict[str, Any]:
    """What a turn leaves behind for the next one (stored as the history entry's session frame)."""
    if status not in ("SUCCESS", "NO_DATA") or strategy not in ("governed", "sql_fallback"):
        return {"question": question.strip(), "standalone_question": (standalone_question or question).strip()}
    return {
        "question": question.strip(),
        "standalone_question": (standalone_question or question).strip(),
        "metric": metric,
        "dimensions": list(dimensions or []),
        "scope": scope or None,
        "period": period or None,
        # Older turns stored these names; the continuation still reads them.
        "last_metric": metric,
        "last_dimensions": list(dimensions or []),
    }


def last_turn(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The previous data turn as {"last_metric", "last_dimensions"}, for the continuation safety net."""
    for entry in reversed(history or []):
        frame = entry.get("session_frame") if isinstance(entry.get("session_frame"), dict) else {}
        metric = frame.get("metric") or frame.get("last_metric")
        if isinstance(metric, str) and metric.strip():
            return {
                "last_metric": metric.strip(),
                "last_dimensions": list(frame.get("dimensions") or frame.get("last_dimensions") or []),
                "last_period": frame.get("period"),
            }
    return None


def last_metric(history: list[dict[str, Any]]) -> str | None:
    previous = last_turn(history)
    return previous["last_metric"] if previous else None


def _short(value: Any, limit: int) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[: limit - 1] + "…"
    return value


def previous_turns(history: list[dict[str, Any]], *, labels: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The last few turns, compact enough for a small model's context."""
    labels = labels or {}
    out: list[dict[str, Any]] = []
    for entry in (history or [])[-_TURNS:]:
        if not isinstance(entry, dict):
            continue
        frame = entry.get("session_frame") if isinstance(entry.get("session_frame"), dict) else {}
        answer = entry.get("answer") if isinstance(entry.get("answer"), dict) else {}
        metric = frame.get("metric") or frame.get("last_metric")
        turn: dict[str, Any] = {"question": _short(entry.get("question"), 300)}
        read_as = frame.get("standalone_question")
        if read_as and read_as != entry.get("question"):
            turn["read_as"] = _short(read_as, 300)
        if metric:
            turn["metric"] = labels.get(str(metric), str(metric))
        if frame.get("dimensions") or frame.get("last_dimensions"):
            turn["breakdown"] = list(frame.get("dimensions") or frame.get("last_dimensions") or [])
        if frame.get("scope"):
            turn["filters_and_period"] = _short(frame["scope"], 300)
        if answer.get("direct_answer"):
            turn["answer"] = _short(answer["direct_answer"], 300)
        if entry.get("strategy") == "agent":
            # An investigation: what it found, so a follow-up on another group or period continues it.
            turn["kind"] = "analysis"
            findings = frame.get("agent_findings") if isinstance(frame.get("agent_findings"), list) else []
            if findings:
                turn["findings"] = findings[:6]
        rows = entry.get("rows") if isinstance(entry.get("rows"), list) else []
        if rows:
            turn["first_rows"] = [
                {str(k): _short(v, 60) for k, v in row.items()} for row in rows[:_ROWS] if isinstance(row, dict)
            ]
        out.append(turn)
    return out


def metric_menu(semantic_context: Any, limit: int = 40) -> list[dict[str, Any]]:
    """Metric names, labels and synonyms of the active model, so the rewrite can name the metric the way the model
    does."""
    from app.ask_data.metric_labels import humanize_metric_label

    try:
        names = sorted(semantic_context.metrics)
    except Exception:
        return []
    menu: list[dict[str, Any]] = []
    for name in names[:limit]:
        try:
            definition = semantic_context.metric_definition(name)
        except Exception:
            continue
        ai = definition.get("ai_context") if isinstance(definition.get("ai_context"), dict) else {}
        menu.append(
            {
                "name": name,
                "label": humanize_metric_label(name=name, definition=definition),
                "synonyms": [str(s) for s in (ai.get("synonyms") or [])][:4],
                "breakdowns": [str(d) for d in definition.get("allowed_dimensions") or []][:12],
            }
        )
    return menu


def metric_labels(semantic_context: Any) -> dict[str, str]:
    return {item["name"]: item["label"] for item in metric_menu(semantic_context)}


def _literal(question: str, *, rationale: str) -> TurnReading:
    kind: Literal["data", "chat"] = "chat" if looks_like_small_talk(question) else "data"
    return TurnReading(kind=kind, uses_previous=False, standalone_question=question.strip(), rationale=rationale)


async def read_turn(
    *,
    provider: LLMProvider,
    question: str,
    history: list[dict[str, Any]] | None,
    semantic_context: Any = None,
) -> TurnReading:
    """Read the new question in the light of the conversation. Never raises: without the model the question is used
    as written."""
    question = question.strip()
    history = [entry for entry in history or [] if isinstance(entry, dict)]
    if looks_like_small_talk(question):
        return _literal(question, rationale="small_talk")
    if not history:
        # A first question has nothing to lean on; it is answered as written.
        return _literal(question, rationale="first_turn")
    menu = metric_menu(semantic_context) if semantic_context is not None else []
    turns = previous_turns(history, labels={item["name"]: item["label"] for item in menu})
    payload = {
        "question": question,
        # The turn a follow-up continues is the last one; older turns are only there to resolve a pointer.
        "last_turn": turns[-1] if turns else None,
        "earlier_turns": turns[:-1],
        "metrics": menu,
    }
    try:
        reading = await provider.generate_structured(
            [
                {"role": "system", "content": PROMPT.read_text(encoding="utf-8")},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
            TurnReading,
            temperature=0.0,
            max_tokens=400,
        )
    except ProviderError as exc:
        logger.warning("conversation_rewrite_failed error=%s", getattr(exc, "code", type(exc).__name__))
        return _literal(question, rationale="rewrite_failed")
    except Exception:
        logger.exception("conversation_rewrite_failed")
        return _literal(question, rationale="rewrite_failed")
    return _settle(question, reading)


def _settle(question: str, reading: TurnReading) -> TurnReading:
    """Guard rails on what the model wrote."""
    rewritten = " ".join((reading.standalone_question or "").split())
    if reading.kind == "chat":
        return TurnReading(kind="chat", uses_previous=False, standalone_question=question, rationale=reading.rationale or "chat")
    kind: Literal["data", "analysis"] = "analysis" if reading.kind == "analysis" else "data"
    if not reading.uses_previous or not rewritten:
        # A question that stands on its own is answered exactly as the user wrote it.
        return TurnReading(kind=kind, uses_previous=False, standalone_question=question, rationale=reading.rationale or "standalone")
    if len(rewritten) > max(400, len(question) * 8):
        return TurnReading(kind=kind, uses_previous=False, standalone_question=question, rationale="rewrite_too_long")
    logger.info("conversation_rewrite question=%r standalone=%r kind=%s", question[:200], rewritten[:300], kind)
    return TurnReading(kind=kind, uses_previous=True, standalone_question=rewritten, rationale=reading.rationale)


def reading_from_state(state: dict[str, Any]) -> TurnReading | None:
    raw = state.get("turn_reading")
    if not isinstance(raw, dict):
        return None
    try:
        return TurnReading.model_validate(raw)
    except Exception:
        return None


CHOICE_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "metric_choice.md"


class MetricChoice(BaseModel):
    metric: str = Field(default="", description="The `name` of the metric that answers the question, or an empty string.")
    confident: bool = Field(default=False, description="True only when one metric clearly fits.")
    candidates: list[str] = Field(
        default_factory=list, description="Up to four metric `name`s that could fit, best first; empty when none fits."
    )
    rationale: str = Field(default="", description="A few words on why.")


class MetricPick(BaseModel):
    """What the language model made of the question: one metric, or the few that could fit."""

    metric: str | None = None
    candidates: list[str] = Field(default_factory=list)


async def pick_metric(*, provider: LLMProvider, question: str, semantic_context: Any) -> MetricPick:
    """When the keyword matcher cannot tell which metric a question is about, the language model reads the question
    against the model's own catalog, the way Genie and Cortex Analyst do. It may only name listed metrics: a sure pick
    is answered straight away, an unsure one narrows the choice shown to the user to the metrics that could fit."""
    menu = metric_menu(semantic_context)
    if not menu:
        return MetricPick()
    names = [item["name"] for item in menu]
    payload = {"question": question, "metrics": [{**item, "description": _description(semantic_context, item["name"])} for item in menu]}
    try:
        choice = await provider.generate_structured(
            [
                {"role": "system", "content": CHOICE_PROMPT.read_text(encoding="utf-8")},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
            MetricChoice,
            temperature=0.0,
            max_tokens=250,
        )
    except ProviderError as exc:
        logger.warning("metric_choice_failed error=%s", getattr(exc, "code", type(exc).__name__))
        return MetricPick()
    except Exception:
        logger.exception("metric_choice_failed")
        return MetricPick()
    picked = (choice.metric or "").strip()
    candidates = [c for c in dict.fromkeys([picked, *(str(c).strip() for c in choice.candidates)]) if c in names][:4]
    logger.info("metric_choice question=%r metric=%r confident=%s candidates=%s", question[:200], picked, choice.confident, candidates)
    return MetricPick(metric=picked if choice.confident and picked in names else None, candidates=candidates)


async def choose_metric(*, provider: LLMProvider, question: str, semantic_context: Any) -> str | None:
    return (await pick_metric(provider=provider, question=question, semantic_context=semantic_context)).metric


def _description(semantic_context: Any, name: str) -> str:
    try:
        return _short(str(semantic_context.metric_definition(name).get("description") or ""), 200)
    except Exception:
        return ""


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).casefold())


def narrow_metric_options(options: list[dict[str, str]], candidates: list[str], semantic_context: Any) -> list[dict[str, str]]:
    """The offered metric options, kept to the candidates the language model named, in its order. An option matches a
    candidate on its id (a registry metric name) or on its shown name (the metric's label or key)."""
    from app.ask_data.metric_labels import humanize_metric_label

    out: list[dict[str, str]] = []
    for name in candidates:
        try:
            label = humanize_metric_label(name=name, definition=semantic_context.metric_definition(name))
        except Exception:
            label = name
        keys = {_norm(name), _norm(label)}
        for option in options:
            if option in out:
                continue
            if _norm(option.get("id", "")) in keys or _norm(option.get("name", "")) in keys:
                out.append(option)
                break
    return out


_MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _one_month(period: str | None) -> tuple[int, int] | None:
    """(year, month) of a period like "2026-06-01 to 2026-06-30"; None for anything wider than one month."""
    dates = re.findall(r"(\d{4})-(\d{2})-(\d{2})", period or "")
    if not dates:
        return None
    months = {(int(y), int(m)) for y, m, _ in dates}
    return next(iter(months)) if len(months) == 1 else None


def comparison_follow_up(raw: str, previous: dict[str, Any] | None, metric_label: str | None) -> str | None:
    """"bisa bandingkan dengan bulan Mei?" right after a June figure: the two months to compare are June (the last turn)
    and May (this message). Written out as a full comparison when the message names one month, no metric, and the last
    turn covered exactly one month."""
    from app.ask_data.comparisons import _COMPARE, detect_period_comparison
    from app.ask_data.intent_satisfaction import parse_requested_constraints

    if not previous or not metric_label or not _COMPARE.search(raw or "") or detect_period_comparison(raw):
        return None
    before = _one_month(previous.get("last_period"))
    if before is None:
        return None
    from app.ask_data.intent_satisfaction import _MONTH_WORDS, _YEARLESS_MONTH

    explicit = parse_requested_constraints(raw).explicit_period
    if explicit and getattr(explicit, "month", None):
        now: tuple[int, int] | None = (explicit.year, explicit.month)
    else:
        months = {_MONTH_WORDS[m.group("m").casefold()] for m in _YEARLESS_MONTH.finditer(raw or "")}
        now = None
        if len(months) == 1:
            month = next(iter(months))
            # The year of the month just asked: "Juni 2026" then "Mei" is May 2026.
            now = (before[0], month)
    if now is None or now == before:
        return None
    first, second = (f"{_MONTHS_EN[m - 1]} {y}" for y, m in (before, now))
    return f"Compare {metric_label} {first} vs {second}"
