from typing import Any
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=500)


class MemoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    memory_type: str = Field(default="general", min_length=1, max_length=80)
    importance: int = Field(default=5, ge=1, le=10)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list, max_length=50)
    source_type: str = Field(default="manual", max_length=80)
    source_ref: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    valid_from: str | None = None
    valid_to: str | None = None
    source_trust: float | None = Field(default=None, ge=0.0, le=1.0)


class MemoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, min_length=1)
    memory_type: str | None = Field(default=None, min_length=1, max_length=80)
    importance: int | None = Field(default=None, ge=1, le=10)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] | None = Field(default=None, max_length=50)
    source_type: str | None = Field(default=None, max_length=80)
    source_ref: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    source_trust: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str | None = Field(default=None, max_length=1000)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5000)
    limit: int = Field(default=10, ge=1, le=50)
    memory_type: str | None = None
    include_documents: bool = True
    include_historical: bool = False


class DeleteRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class RejectRequest(BaseModel):
    reason: str = Field(default="Rejected by administrator", min_length=3, max_length=1000)


class RelationCreate(BaseModel):
    target_memory_id: str
    relation_type: str = Field(min_length=1, max_length=100)


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(min_length=1, max_length=20)


class ChatImportCreate(BaseModel):
    source_document_id: str


class CandidateUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, min_length=1)
    memory_type: str | None = Field(default=None, min_length=1, max_length=80)
    importance: int | None = Field(default=None, ge=1, le=10)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] | None = Field(default=None, max_length=50)


class SafeAcceptRequest(BaseModel):
    import_job_id: str | None = None


class MemorySupersede(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    memory_type: str | None = Field(default=None, max_length=80)
    importance: int | None = Field(default=None, ge=1, le=10)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list, max_length=50)
    source_type: str | None = Field(default=None, max_length=80)
    source_ref: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    valid_from: str | None = None
    valid_to: str | None = None
    source_trust: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str | None = Field(default='Superseded by newer information', max_length=1000)


class EntityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    entity_type: str = Field(default='other', min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    aliases: list[str] = Field(default_factory=list, max_length=30)


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    event_type: str = Field(default='event', min_length=1, max_length=80)
    occurred_at: str | None = None
    ended_at: str | None = None
    importance: int = Field(default=5, ge=1, le=10)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorCreate(BaseModel):
    connector_type: str = Field(default="github", min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    schedule_minutes: int = Field(default=30, ge=5, le=10080)
    config: dict[str, Any] = Field(default_factory=dict)


class ConnectorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    schedule_minutes: int | None = Field(default=None, ge=5, le=10080)
    config: dict[str, Any] | None = None


class GmailOAuthStart(BaseModel):
    name: str = Field(default="Gmail", min_length=1, max_length=200)
    query: str = Field(default="newer_than:30d", max_length=1000)
    label_ids: list[str] = Field(default_factory=lambda: ["INBOX"], max_length=20)
    max_messages_per_sync: int = Field(default=100, ge=1, le=500)


class CaptureCreate(BaseModel):
    capture_type: str = Field(default="page", pattern="^(page|selection|link|note)$")
    title: str = Field(min_length=1, max_length=500)
    url: str | None = Field(default=None, max_length=4000)
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OAuthClientCreate(BaseModel):
    client_name: str = Field(min_length=1, max_length=300)
    redirect_uris: list[str] = Field(min_length=1, max_length=20)
    allowed_scopes: list[str] = Field(
        default_factory=lambda: [
            "mcp:use",
            "memory:read",
            "document:read",
        ],
        min_length=1,
        max_length=20,
    )


class OAuthClientUpdate(BaseModel):
    client_name: str | None = Field(default=None, min_length=1, max_length=300)
    redirect_uris: list[str] | None = Field(default=None, min_length=1, max_length=20)
    allowed_scopes: list[str] | None = Field(default=None, min_length=1, max_length=20)
    is_active: bool | None = None
