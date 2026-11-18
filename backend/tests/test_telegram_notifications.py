import json
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

from app import telegram_notifications as telegram


def test_telegram_sends_only_plain_generic_message_to_fixed_origin(monkeypatch):
    monkeypatch.setattr(telegram, "settings", lambda: SimpleNamespace(telegram_bot_token="fixture"))
    connection = MagicMock()
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.read.return_value = b'{"ok":true}'
    with patch.object(telegram, "HTTPSConnection", return_value=connection) as factory:
        telegram.send("-123", "Engram test")
    factory.assert_called_once_with("api.telegram.org", timeout=10)
    args, kwargs = connection.request.call_args
    assert args == ("POST", "/botfixture/sendMessage")
    data = json.loads(kwargs["body"])
    assert data["chat_id"] == "-123"
    assert "parse_mode" not in data and data["protect_content"] is True
    assert data["link_preview_options"]["is_disabled"] is True
    connection.close.assert_called_once()


def test_telegram_rejects_invalid_destination_and_redacts_provider_failures(monkeypatch):
    monkeypatch.setattr(telegram, "settings", lambda: SimpleNamespace(telegram_bot_token="secret-fixture"))
    with pytest.raises(HTTPException) as error:
        telegram.send("https://attacker.invalid", "test")
    assert error.value.status_code == 422
    connection = MagicMock()
    connection.getresponse.return_value.status = 403
    connection.getresponse.return_value.read.return_value = b'{"ok":false,"description":"secret-fixture"}'
    with patch.object(telegram, "HTTPSConnection", return_value=connection):
        with pytest.raises(HTTPException) as error:
            telegram.send("123", "test")
        assert error.value.status_code == 502
        assert "secret-fixture" not in error.value.detail
    connection.close.assert_called_once()
