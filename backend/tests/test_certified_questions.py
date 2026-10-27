from app.semantic_runtime.certified_questions import build_certified_golden_questions


def test_certified_questions_from_starter_settings() -> None:
    class _Ws:
        settings_json = {
            "ask_data": {
                "starter_questions": ["What is the total transaction amount?"],
                "starter_source": "configured",
            }
        }

    class _Session:
        def get(self, _cls, _id):
            return _Ws()

    class _Model:
        key = "banking_analytics"

    out = build_certified_golden_questions(_Session(), workspace_id="00000000-0000-0000-0000-000000000001", model=_Model())  # type: ignore[arg-type]
    assert len(out) == 1
    assert out[0]["certified"] is True
    assert "total transaction amount" in out[0]["question"].casefold()
