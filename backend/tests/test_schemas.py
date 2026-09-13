import pytest
from pydantic import ValidationError

from app.schemas import (
    ApiKeyCreate,
    CaptureCreate,
    ConnectorCreate,
    LoginRequest,
    MemoryCreate,
    MemoryUpdate,
    OAuthClientCreate,
    SearchRequest,
)


def test_memory_create_defaults_are_safe():
    memory = MemoryCreate(title="Test memory", content="Useful content")

    assert memory.memory_type == "general"
    assert memory.importance == 5
    assert memory.confidence == 1.0
    assert memory.tags == []
    assert memory.source_type == "manual"


@pytest.mark.parametrize("importance", [0, 11])
def test_memory_create_rejects_out_of_range_importance(importance):
    with pytest.raises(ValidationError):
        MemoryCreate(
            title="Test memory",
            content="Useful content",
            importance=importance,
        )


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_memory_create_rejects_out_of_range_confidence(confidence):
    with pytest.raises(ValidationError):
        MemoryCreate(
            title="Test memory",
            content="Useful content",
            confidence=confidence,
        )


def test_login_requires_reasonable_password_length():
    with pytest.raises(ValidationError):
        LoginRequest(username="jayden", password="short")


@pytest.mark.parametrize("limit", [0, 51])
def test_search_limit_is_bounded(limit):
    with pytest.raises(ValidationError):
        SearchRequest(query="memory", limit=limit)


def test_capture_type_is_restricted():
    with pytest.raises(ValidationError):
        CaptureCreate(
            capture_type="screenshot",
            title="Test capture",
            text="Captured text",
        )


def test_connector_schedule_has_minimum_interval():
    with pytest.raises(ValidationError):
        ConnectorCreate(name="GitHub", schedule_minutes=4)


def test_api_key_requires_at_least_one_scope():
    with pytest.raises(ValidationError):
        ApiKeyCreate(name="CI key", scopes=[])


def test_oauth_client_gets_least_privilege_default_scopes():
    client = OAuthClientCreate(
        client_name="Test MCP client",
        redirect_uris=["https://example.invalid/callback"],
    )

    assert client.allowed_scopes == [
        "mcp:use",
        "memory:read",
        "document:read",
    ]


def test_memory_update_allows_partial_updates():
    update = MemoryUpdate(importance=7)

    assert update.importance == 7
    assert update.title is None
