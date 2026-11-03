from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("eval_retrieval", REPO / "scripts" / "eval_retrieval.py")
ev = importlib.util.module_from_spec(_spec)
sys.modules["eval_retrieval"] = ev
_spec.loader.exec_module(ev)


def _results(*pages: int, name: str = "Policy.pdf") -> list[dict]:
    return [{"filename": name, "page_number": page} for page in pages]


def test_the_expected_passage_is_found_by_file_and_page() -> None:
    assert ev.rank_of_expected(_results(3, 1, 2), {"filename": "policy", "page": 1}) == 2
    assert ev.rank_of_expected(_results(3, 1, 2), {"filename": "policy"}) == 1  # no page: any page of the file counts
    assert ev.rank_of_expected(_results(3, 1), {"filename": "other", "page": 1}) is None
    assert ev.rank_of_expected([], {"filename": "policy", "page": 1}) is None


def test_the_summary_counts_hits_and_mean_reciprocal_rank() -> None:
    summary = ev.summarize([1, 3, None, 5], [10.0, 20.0, 30.0, 40.0])
    assert summary == {"questions": 4, "hit@1": 0.25, "hit@3": 0.5, "hit@5": 0.75, "mrr": round((1 + 1 / 3 + 1 / 5) / 4, 3), "mean_ms": 25.0}


def test_a_run_uses_the_backends_own_timing_and_names_the_reranker() -> None:
    answers = {
        "q1": {"results": _results(1), "metadata": {"reranker_model": "bge", "total_retrieval_ms": 120}},
        "q2": {"results": _results(4, 2), "metadata": {"reranker_model": "bge", "total_retrieval_ms": 80}},
    }
    questions = [
        {"question": "q1", "expect": {"filename": "policy", "page": 1}},
        {"question": "q2", "expect": {"filename": "policy", "page": 2}},
    ]
    result = ev.evaluate(lambda query: answers[query], questions)
    assert result["reranker"] == "bge"
    assert [row["rank"] for row in result["details"]] == [1, 2]
    assert result["summary"]["mean_ms"] == 100.0 and result["summary"]["hit@1"] == 0.5


def test_the_sample_questions_point_at_the_five_policy_pages() -> None:
    questions = json.loads((REPO / "samples" / "fulfillment" / "retrieval_eval.json").read_text())
    assert {q["expect"]["page"] for q in questions} == {1, 2, 3, 4, 5}
    assert all(q["question"] and q["expect"]["filename"] for q in questions)


def test_without_a_url_or_a_project_it_asks_for_one(capsys, monkeypatch) -> None:
    monkeypatch.delenv("CDSW_DOMAIN", raising=False)
    assert ev.main(["--questions", str(REPO / "samples" / "fulfillment" / "retrieval_eval.json")]) == 2
    assert "--base-url" in capsys.readouterr().err
    assert ev.main(["-f", "/tmp/kernel.json", "--questions", "x.json"]) == 2  # the kernel's argument is ignored
