#!/usr/bin/env python3
"""Measure how well Knowledge search finds the right passage, so a reranker can be judged on your own documents.

You give it questions and where the answer is (file and page). It asks the Backend's search for each one and reports how often
the right passage is first (hit@1), in the top 3 and top 5 (hit@3, hit@5), the mean reciprocal rank (MRR) and the search time.
Run it once with the reranker off and once with it on (ENABLE_RERANKER), same questions, and compare.

Usage (in a Cloudera AI Session, from the project root):
  python scripts/eval_retrieval.py --questions samples/fulfillment/retrieval_eval.json --label reranker-off
  python scripts/eval_retrieval.py --questions samples/fulfillment/retrieval_eval.json --label reranker-on --out on.json
Elsewhere pass --base-url https://<backend-app-url>/<secret>. The secret is never printed.

Questions file: a JSON list of {"question": "...", "expect": {"filename": "Policy.pdf", "page": 2}} ("page" is optional).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent


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


def matches(result: dict[str, Any], expect: dict[str, Any]) -> bool:
    name = str(expect.get("filename") or "").casefold()
    if name and name not in str(result.get("filename") or "").casefold():
        return False
    page = expect.get("page")
    return page is None or result.get("page_number") == page


def rank_of_expected(results: list[dict[str, Any]], expect: dict[str, Any]) -> int | None:
    """1-based position of the first result that is the expected passage, or None."""
    for position, result in enumerate(results, 1):
        if matches(result, expect):
            return position
    return None


def summarize(ranks: list[int | None], milliseconds: list[float]) -> dict[str, Any]:
    total = len(ranks) or 1
    return {
        "questions": len(ranks),
        "hit@1": round(sum(1 for r in ranks if r == 1) / total, 3),
        "hit@3": round(sum(1 for r in ranks if r is not None and r <= 3) / total, 3),
        "hit@5": round(sum(1 for r in ranks if r is not None and r <= 5) / total, 3),
        "mrr": round(sum(1.0 / r for r in ranks if r) / total, 3),
        "mean_ms": round(sum(milliseconds) / (len(milliseconds) or 1), 1),
    }


def evaluate(search: Callable[[str], dict[str, Any]], questions: list[dict[str, Any]]) -> dict[str, Any]:
    ranks: list[int | None] = []
    times: list[float] = []
    details: list[dict[str, Any]] = []
    reranker = ""
    for item in questions:
        started = time.perf_counter()
        response = search(item["question"])
        elapsed = (time.perf_counter() - started) * 1000
        meta = response.get("metadata") or {}
        reranker = str(meta.get("reranker_model") or reranker)
        measured = meta.get("total_retrieval_ms")
        times.append(float(measured) if isinstance(measured, (int, float)) else elapsed)
        rank = rank_of_expected(response.get("results") or [], item.get("expect") or {})
        ranks.append(rank)
        details.append({"question": item["question"], "rank": rank})
    return {"reranker": reranker or "unknown", "summary": summarize(ranks, times), "details": details}


def http_search(base_url: str, library_ids: list[str] | None, top_k: int | None) -> Callable[[str], dict[str, Any]]:
    def search(query: str) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query}
        if library_ids:
            body["library_ids"] = library_ids
        if top_k:
            body["top_k"] = top_k
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/v1/retrieval/search",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - the Backend URL the operator passes
            return json.loads(response.read().decode())

    return search


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--questions", required=True, help="JSON list of questions and the expected file and page")
    parser.add_argument("--base-url", help="Backend URL including its secret path (default: derived inside a Cloudera AI project)")
    parser.add_argument("--library-id", action="append", help="limit the search to this library (repeatable)")
    parser.add_argument("--top-k", type=int, help="candidates to fetch before reranking (default: the Backend setting)")
    parser.add_argument("--label", default="run", help="a name for this run, for example reranker-off")
    parser.add_argument("--out", help="write the full result as JSON")
    args, _ = parser.parse_known_args(argv)  # the IPython kernel that runs CAI jobs adds '-f <kernel.json>'
    base_url = args.base_url or default_base_url(dict(os.environ))
    if not base_url:
        print("Pass --base-url (the Backend URL with its secret), or run this inside a Cloudera AI project.", file=sys.stderr)
        return 2
    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    try:
        result = evaluate(http_search(base_url, args.library_id, args.top_k), questions)
    except OSError as exc:
        print(f"FAILED: could not reach the Backend search ({type(exc).__name__}).", file=sys.stderr)
        return 1
    result["label"] = args.label
    print(f"[{args.label}] reranker: {result['reranker']}")
    for row in result["details"]:
        print(f"  rank {row['rank'] if row['rank'] else '-':>2}  {row['question']}")
    print("summary:", json.dumps(result["summary"]))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    code = main(sys.argv[1:])
    if code:
        sys.exit(code)
