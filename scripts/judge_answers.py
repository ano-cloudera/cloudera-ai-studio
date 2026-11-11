#!/usr/bin/env python3
"""Judge Ask Data answers against an answer key, so "the tests pass" also means "the answers are right".

A case file is one conversation: questions asked in order in one session, each with what a correct answer must show
(the route it takes, the metric, the top row, the numbers the text must state, words it must and must not use). The
script asks the Backend each question, checks the answer and prints one line per question with every failed check.
The numbers come from the sample data, so a wrong figure, an English answer to an Indonesian question, a breakdown
that lost its dimension or an open question answered with one figure all show up as a failure.

Usage (in a Cloudera AI Session, from the project root):
  python scripts/judge_answers.py --cases samples/fulfillment/judge_conversation.json
  python scripts/judge_answers.py --cases samples/fulfillment/judge_conversation.json --out judge.json
Elsewhere pass --base-url https://<backend-app-url>/<secret>. The secret is never printed. --provider and --model pick
the model (default: the first available one the Backend lists, Qwen first).

Checks in "expect" (all optional): route (chat, data, agent), status (one or a list), metric (any of), first_row (a
value in the first row), min_rows, overall_value, min_steps (agent steps), numbers (each must appear in the text,
rounding allowed), numbers_any (any one group of numbers must all appear), mentions (each item a phrase or a list of
alternatives), forbids (phrases that must not appear), forbids_numbers, needs_actions (business implications given).
Every answer is also checked for the language of the case file and for a line that only repeats its own label.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent

_ROUTES = {"chat": {"conversational"}, "agent": {"agent"}, "data": {"governed", "sql_fallback"}}
# Words that only an English sentence uses; metric names ("Late Delivery Rate") are fine in an Indonesian answer.
_ENGLISH = re.compile(r"\b(the|is|are|was|were|which|with|this|that|these|there|than|from|of|and|by|for|in|to|has|have|shows?)\b", re.I)
_NUMBER = re.compile(r"(?<![\w.,])-?\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|(?<![\w.,])-?\d+(?:[.,]\d+)?")


def default_base_url(env: dict[str, str]) -> str | None:
    """The Backend URL with its secret path, derived exactly as the deploy Job does (only inside a Cloudera AI project)."""
    domain = env.get("CDSW_DOMAIN", "").strip()
    if not domain:
        return None
    sys.path.insert(0, str(HERE / "amp"))
    import deploy  # noqa: PLC0415 - the deploy Job owns the secret handling

    prefix = env.get("AMP_SUBDOMAIN_PREFIX", "").strip() or "anywhere"
    token = env.get("STUDIO_API_TOKEN") or deploy.derive(deploy.studio_secret(env), "backend")
    return f"https://{prefix}-backend.{domain}/{token}"


def answer_text(response: dict[str, Any]) -> str:
    answer = response.get("answer") or {}
    parts: list[str] = [str(answer.get("direct_answer") or ""), str(answer.get("executive_summary") or "")]
    for key in ("insights", "business_implications", "caveats"):
        parts.extend(str(item) for item in answer.get(key) or [])
    return "\n".join(p for p in parts if p.strip())


def numbers_in(text: str) -> list[float]:
    """Every number in the text, reading "23,15" and "23.15" alike and "1.074" / "1,074" as thousands."""
    found: list[float] = []
    for token in _NUMBER.findall(text):
        cleaned = token
        if re.fullmatch(r"-?\d{1,3}(?:[.,]\d{3})+", token):
            cleaned = re.sub(r"[.,]", "", token)
        elif "," in token and "." in token:  # "11.716,55" and "11,716.55": the last separator is the decimal one
            last = max(token.rfind(","), token.rfind("."))
            cleaned = re.sub(r"[.,]", "", token[:last]) + "." + token[last + 1 :]
        else:
            cleaned = token.replace(",", ".")
        try:
            found.append(float(cleaned))
        except ValueError:
            continue
    return found


def states_number(text: str, expected: float) -> bool:
    """The text gives the number with one or two decimals ("23.15" as 23.15, 23.2 or 23.1; "23,15" alike)."""
    return any(abs(value - expected) <= 0.06 for value in numbers_in(text))


def _has(text: str, phrase: str | list[str]) -> bool:
    options = phrase if isinstance(phrase, list) else [phrase]
    folded = text.casefold()
    return any(str(option).casefold() in folded for option in options)


def echoed_labels(text: str) -> list[str]:
    """Lines that only repeat their own label ("Late Rate By Attributes: Late Rate by Attributes (%)")."""
    out = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        label, _, rest = line.partition(":")
        strip = lambda s: re.sub(r"[^a-z0-9]+", " ", re.sub(r"\(.*?\)", "", s.casefold())).strip()  # noqa: E731
        if strip(label) and strip(label.lstrip("-*• ")) == strip(rest):
            out.append(line.strip())
    return out


def english_words(text: str) -> int:
    return len(_ENGLISH.findall(text))


def judge(expect: dict[str, Any], response: dict[str, Any], *, language: str = "id") -> list[tuple[str, bool, str]]:
    """Every check for one answer as (name, passed, what was seen)."""
    checks: list[tuple[str, bool, str]] = []
    status = str(response.get("status") or "")
    strategy = str(response.get("strategy") or "")
    data = response.get("data") or {}
    rows = data.get("rows") or []
    text = answer_text(response)

    wanted_status = expect.get("status") or ["SUCCESS"]
    wanted_status = wanted_status if isinstance(wanted_status, list) else [wanted_status]
    checks.append(("status", status in wanted_status, status))
    checks.append(("answered", bool(text.strip()), f"{len(text)} chars"))
    if "route" in expect:
        checks.append(("route", strategy in _ROUTES.get(expect["route"], {expect["route"]}), f"{expect['route']} wanted, strategy={strategy}"))
    if "metric" in expect:
        metric = str(data.get("governed_metric") or "")
        checks.append(("metric", metric in expect["metric"], metric or "none"))
    if "first_row" in expect:
        first = rows[0] if rows else {}
        checks.append(("first_row", any(str(v) == expect["first_row"] for v in first.values()), json.dumps(first, default=str)[:120]))
    if "min_rows" in expect:
        checks.append(("rows", len(rows) >= expect["min_rows"], f"{len(rows)} rows, {expect['min_rows']} wanted"))
    if "overall_value" in expect:
        seen = data.get("overall_value")
        checks.append(("overall_value", seen is not None and abs(float(seen) - expect["overall_value"]) < 0.06, str(seen)))
    if "min_steps" in expect:
        steps = (response.get("calculation") or {}).get("steps") or []
        checks.append(("steps", strategy == "agent" and len(steps) >= expect["min_steps"], f"{len(steps)} steps"))
    for number in expect.get("numbers") or []:
        checks.append((f"states {number}", states_number(text, float(number)), "not in the text" if not states_number(text, float(number)) else "ok"))
    if expect.get("numbers_any"):
        groups = expect["numbers_any"]
        ok = any(all(states_number(text, float(n)) for n in group) for group in groups)
        checks.append(("states one of " + " / ".join(str(g) for g in groups), ok, "ok" if ok else "none of the groups"))
    for phrase in expect.get("mentions") or []:
        checks.append((f"mentions {phrase if isinstance(phrase, str) else ' | '.join(phrase)}", _has(text, phrase), "ok" if _has(text, phrase) else "missing"))
    for phrase in expect.get("forbids") or []:
        checks.append((f"avoids {phrase!r}", not _has(text, phrase), "ok" if not _has(text, phrase) else "present"))
    for number in expect.get("forbids_numbers") or []:
        direct = str((response.get("answer") or {}).get("direct_answer") or "")
        bad = any(abs(v - float(number)) < 1e-9 for v in numbers_in(re.sub(r"20\d\d", "", direct)))
        checks.append((f"does not answer {number}", not bad, "ok" if not bad else "answered with it"))
    if expect.get("needs_actions"):
        actions = (response.get("answer") or {}).get("business_implications") or []
        checks.append(("actions", len(actions) >= 1, f"{len(actions)} actions"))
    if language == "id" and text.strip():
        count = english_words(text)
        checks.append(("language id", count <= 3, f"{count} English words"))
    echoes = echoed_labels(text)
    checks.append(("no repeated labels", not echoes, "; ".join(echoes)[:160] or "ok"))
    if "—" in text:
        checks.append(("no em dash", False, "em dash present"))
    return checks


def run_conversation(ask: Callable[[str, str], dict[str, Any]], cases: dict[str, Any]) -> dict[str, Any]:
    session = f"judge-{uuid.uuid4().hex[:8]}"
    language = cases.get("language", "id")
    turns = []
    for index, turn in enumerate(cases["turns"], 1):
        started = time.perf_counter()
        try:
            response = ask(turn["question"], session)
            error = None
        except Exception as exc:  # noqa: BLE001 - one failing question must not stop the run
            response, error = {}, f"{type(exc).__name__}: {exc}"[:200]
        seconds = round(time.perf_counter() - started, 1)
        checks = judge(turn.get("expect") or {}, response, language=language)
        if error:
            checks.insert(0, ("request", False, error))
        turns.append({
            "turn": index,
            "question": turn["question"],
            "passed": all(ok for _, ok, _ in checks),
            "seconds": seconds,
            "strategy": response.get("strategy"),
            "metric": (response.get("data") or {}).get("governed_metric"),
            "failed": [{"check": name, "seen": seen} for name, ok, seen in checks if not ok],
            "checks": len(checks),
            "answer": answer_text(response)[:1500],
            "rows": ((response.get("data") or {}).get("rows") or [])[:10],
            "steps": (response.get("calculation") or {}).get("steps") or [],
        })
    passed = sum(1 for t in turns if t["passed"])
    return {"name": cases.get("name"), "session": session, "passed": passed, "total": len(turns), "turns": turns}


def http_ask(base_url: str, provider: str, model: str) -> Callable[[str, str], dict[str, Any]]:
    def ask(question: str, session: str) -> dict[str, Any]:
        body = {"session_id": session, "question": question, "provider": provider, "model": model}
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310 - the Backend URL the operator passes
            return json.loads(response.read().decode())

    return ask


def pick_model(base_url: str) -> tuple[str, str] | None:
    with urllib.request.urlopen(f"{base_url.rstrip('/')}/models", timeout=60) as response:  # noqa: S310
        models = [m for m in json.loads(response.read().decode()).get("models", []) if m.get("available")]
    models.sort(key=lambda m: m.get("provider") != "qwen")
    return (models[0]["provider"], models[0]["id"]) if models else None


def print_report(result: dict[str, Any]) -> None:
    print(f"{result['name']}: {result['passed']} of {result['total']} answers pass")
    for turn in result["turns"]:
        mark = "PASS" if turn["passed"] else "FAIL"
        print(f"{mark} {turn['turn']:>2}. {turn['question'][:70]}  [{turn['strategy']}, {turn['seconds']}s]")
        for failure in turn["failed"]:
            print(f"        - {failure['check']}: {failure['seen']}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cases", required=True, help="the conversation and its answer key (JSON)")
    parser.add_argument("--base-url", help="Backend URL including its secret path (default: derived inside a Cloudera AI project)")
    parser.add_argument("--provider", help="qwen, gemini or openai (default: the first available model)")
    parser.add_argument("--model", help="model id as the Backend lists it under /models")
    parser.add_argument("--out", help="write every answer and check as JSON, to send back for review")
    args, _ = parser.parse_known_args(argv)  # the IPython kernel that runs CAI jobs adds '-f <kernel.json>'
    base_url = args.base_url or default_base_url(dict(os.environ))
    if not base_url:
        print("Pass --base-url (the Backend URL with its secret), or run this inside a Cloudera AI project.", file=sys.stderr)
        return 2
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    try:
        selection = (args.provider, args.model) if args.provider and args.model else pick_model(base_url)
    except OSError as exc:
        print(f"FAILED: could not reach the Backend ({type(exc).__name__}).", file=sys.stderr)
        return 1
    if not selection:
        print("No available model is listed by the Backend; pass --provider and --model.", file=sys.stderr)
        return 1
    print(f"model: {selection[0]} {selection[1]}")
    result = run_conversation(http_ask(base_url, *selection), cases)
    result["model"] = {"provider": selection[0], "id": selection[1]}
    print_report(result)
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"written: {args.out}")
    return 0 if result["passed"] == result["total"] else 3


if __name__ == "__main__":
    code = main(sys.argv[1:])
    if code:
        sys.exit(code)
