from unittest.mock import patch
import pytest
from fastapi import HTTPException
from app import ask

SOURCE = {"id": "memory-one", "title": "Launch decision", "content": "We decided to launch on Friday after the review.", "updated_at": "2026-09-30T12:00:00Z"}


def test_answer_uses_retrieved_sources_and_checks_exact_evidence():
    generated = {"claims": [{"text": "The launch is Friday.", "source": 1, "quote": "launch on Friday after the review"}], "insufficient": False}
    with patch.object(ask.memories, "search", return_value=[SOURCE]) as search, patch.object(ask, "_ollama_json", return_value=generated) as model:
        result = ask.answer("When is launch?")
    search.assert_called_once_with("When is launch?", 5, None)
    assert result["claims"] == generated["claims"]
    assert result["sources"][0]["id"] == SOURCE["id"]
    assert SOURCE["content"] in model.call_args.args[1]


@pytest.mark.parametrize("source,quote", [(99, "launch on Friday"), (True, "launch on Friday"), (1, "launch on Monday"), (1, "Friday")])
def test_invalid_citations_do_not_become_an_answer(source, quote):
    with patch.object(ask.memories, "search", return_value=[SOURCE]), patch.object(ask, "_ollama_json", return_value={"claims": [{"text": "Invented answer", "source": source, "quote": quote}], "insufficient": False}):
        with pytest.raises(HTTPException) as error:
            ask.answer("When is launch?")
    assert error.value.status_code == 502


def test_empty_project_does_not_call_the_model():
    with patch.object(ask.memories, "search", return_value=[]), patch.object(ask, "_ollama_json") as model:
        assert ask.answer("When is launch?")["insufficient"] is True
    model.assert_not_called()


def test_unavailable_model_returns_an_actionable_error():
    with patch.object(ask.memories, "search", return_value=[SOURCE]), patch.object(ask, "_ollama_json", side_effect=RuntimeError("offline")):
        with pytest.raises(HTTPException) as error:
            ask.answer("When is launch?")
    assert error.value.status_code == 503
