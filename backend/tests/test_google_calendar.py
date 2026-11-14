import hashlib
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException

from app import connectors


def test_calendar_requests_its_own_read_only_scope_and_pkce(monkeypatch):
    monkeypatch.setattr(connectors, "settings", lambda: SimpleNamespace(
        google_calendar_client_id="calendar-test", google_calendar_client_secret="test",
        public_origin="https://engram.example.invalid", redis_url="redis://test",
    ))
    monkeypatch.setattr(connectors, "_google_encryption_key", lambda: b"x" * 32)
    monkeypatch.setattr(connectors.Redis, "from_url", lambda _: SimpleNamespace(set=lambda *a, **kw: True))
    url = connectors.start_google_oauth("google_calendar", {}, "test", "test", "session")
    params = parse_qs(urlsplit(url).query)
    assert params["scope"] == [connectors.CALENDAR_SCOPE]
    assert params["client_id"] == ["calendar-test"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["https://engram.example.invalid" + connectors.CALENDAR_CALLBACK_PATH]


def test_calendar_sync_preserves_event_details_and_paginates():
    results = []

    def handle(request):
        assert request.url.path.endswith("/calendars/primary/events")
        assert request.url.params["singleEvents"] == "true"
        if request.url.params.get("pageToken") == "next":
            return httpx.Response(200, json={"items": [{"id": "cancelled", "status": "cancelled"}]})
        return httpx.Response(200, json={"nextPageToken": "next", "items": [{
            "id": "event", "summary": "Project review", "start": {"date": "2026-11-20"},
            "end": {"date": "2026-11-21"}, "description": "<p>Review notes</p>",
            "location": "Room 2", "attendees": [{"email": "person@example.invalid"}],
            "recurringEventId": "series",
        }]})

    client = httpx.Client(base_url="https://www.googleapis.com/calendar/v3/", transport=httpx.MockTransport(handle))
    counters = {"seen": 0, "changed": 0, "skipped": 0, "errors": 0}
    with patch.object(connectors.httpx, "Client", return_value=client), \
         patch.object(connectors, "_google_access_token", return_value="fixture"), \
         patch.object(connectors, "_upsert_source_item", side_effect=lambda *a, **kw: results.append((a, kw)) or True):
        connectors._sync_google_calendar({"config": {}}, "run", counters)
    assert counters == {"seen": 2, "changed": 1, "skipped": 1, "errors": 0}
    args, kwargs = results[0]
    assert b"2026-11-20" in args[6] and b"Review notes" in args[6]
    assert args[-1]["recurring_event_id"] == "series"
    assert kwargs["source_type"] == "google_calendar"

@pytest.mark.parametrize(
    ("kind", "project_id", "session", "expected_status"),
    [
        ("gmail", "project-a", "browser-a", 400),
        ("google_calendar", "project-b", "browser-a", 409),
        ("google_calendar", "project-a", "browser-b", 403),
    ],
)
def test_calendar_rejects_mismatched_oauth_context(
    monkeypatch, kind, project_id, session, expected_status
):
    state_hash = hashlib.sha256(b"state").hexdigest()
    states = {f"google_calendar:oauth:{state_hash}": json.dumps({
        "project_id": "project-a", "session_hash": "browser-a", "verifier": "pkce",
    })}
    monkeypatch.setattr(connectors, "settings", lambda: SimpleNamespace(redis_url="redis://test"))
    monkeypatch.setattr(connectors, "_google_client_credentials", lambda _: ("client", "secret"))
    monkeypatch.setattr(connectors, "current_project_id", lambda: project_id)
    monkeypatch.setattr(connectors.Redis, "from_url", lambda _: SimpleNamespace(
        getdel=lambda key: states.pop(key, None),
    ))

    with patch.object(connectors.httpx, "post") as exchange:
        with pytest.raises(HTTPException) as error:
            connectors.finish_google_oauth(kind, "state", "code", session)
        assert error.value.status_code == expected_status
        exchange.assert_not_called()
