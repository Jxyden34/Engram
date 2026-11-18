from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException

from app import telegram_notifications as telegram


def test_telegram_sends_only_plain_generic_message_to_fixed_origin(monkeypatch):
    monkeypatch.setattr(telegram, "settings", lambda: SimpleNamespace(telegram_bot_token="fixture"))
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url.host == "api.telegram.org"
        assert request.url.path == "/botfixture/sendMessage"
        data = __import__("json").loads(request.content)
        assert data["chat_id"] == "-123"
        assert "parse_mode" not in data
        assert data["protect_content"] is True
        assert data["link_preview_options"]["is_disabled"] is True
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    with patch.object(telegram.httpx, "Client", return_value=client):
        telegram.send("-123", "Engram test")
    assert len(requests) == 1


def test_telegram_rejects_invalid_destination_and_redacts_provider_failures(monkeypatch):
    monkeypatch.setattr(telegram, "settings", lambda: SimpleNamespace(telegram_bot_token="secret-fixture"))
    with pytest.raises(HTTPException) as error:
        telegram.send("https://attacker.invalid", "test")
    assert error.value.status_code == 422

    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        403, json={"ok": False, "description": "secret-fixture"})))
    with patch.object(telegram.httpx, "Client", return_value=client):
        with pytest.raises(HTTPException) as error:
            telegram.send("123", "test")
        assert error.value.status_code == 502
        assert "secret-fixture" not in error.value.detail
