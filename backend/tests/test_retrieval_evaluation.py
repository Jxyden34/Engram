from scripts.evaluate_hindsight import source_ids


def test_recall_counts_source_documents_not_multiple_facts_from_one_document():
    rows = [{"document_id": "memory:a"}, {"document_id": "memory:a"},
            {"metadata": {"engram_memory_id": "b"}},
            {"document_id": None, "metadata": None}]
    assert source_ids(rows) == ["a", "b"]


def test_recall_limit_applies_after_source_deduplication():
    rows = [{"document_id": "memory:a"}] * 10
    rows += [{"document_id": "memory:" + key} for key in "bcdef"]
    assert source_ids(rows) == list("abcde")
