from datetime import datetime, timezone
from unittest.mock import patch

import httpx

from app import connectors


def test_backfill_preserves_labels_and_bounds_message_requests():
    synced = []
    connector = {
        "config": {"email_address": "test@example.invalid", "query": "newer_than:30d",
                   "label_ids": ["STARRED"], "max_messages_per_sync": 2},
    }
    first = int(datetime(2025, 4, 10, tzinfo=timezone.utc).timestamp())

    def handle(request):
        if request.url.path.endswith("/messages"):
            assert request.url.params["q"] == f"after:{first - 1} before:{first + 86400}"
            assert request.url.params.get_list("labelIds") == ["STARRED"]
            return httpx.Response(200, json={"messages": [{"id": "first"}, {"id": "gone"}, {"id": "extra"}]})
        if request.url.path.endswith("/first"):
            return httpx.Response(200, json={"internalDate": str(first * 1000), "snippet": "Fixture"})
        if request.url.path.endswith("/gone"):
            return httpx.Response(404)
        raise AssertionError("The third message exceeds the sync limit")

    client = httpx.Client(base_url="https://gmail.googleapis.com/gmail/v1/users/me/",
                          transport=httpx.MockTransport(handle))
    counters = {"seen": 0, "changed": 0, "skipped": 0, "errors": 0}
    with patch.object(connectors.httpx, "Client", return_value=client), \
         patch.object(connectors, "_gmail_access_token", return_value="fixture"), \
         patch.object(connectors, "_upsert_source_item", side_effect=lambda *args, **kwargs: synced.append(args) or True):
        connectors._sync_gmail(connector, "run", counters, ("2025-04-10", "2025-04-10"))
    assert counters == {"seen": 1, "changed": 1, "skipped": 1, "errors": 0}
    assert synced[0][2] == "gmail:test@example.invalid:first"
