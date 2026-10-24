from typing import Any, Literal
from uuid import UUID
from datetime import date, datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, model_validator


class LicenseActivation(BaseModel):
    mode: Literal["personal", "commercial"]
    license_key: str | None = Field(default=None, max_length=8192)


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
    include_archived: bool = False


class ArchiveRequest(BaseModel):
    archived: bool
    expected_updated_at: datetime
    reason: str = Field(min_length=3, max_length=1000)


class PinRequest(BaseModel):
    pinned: bool
    expected_updated_at: datetime


class ClusterDraftRequest(BaseModel):
    memory_ids: list[UUID] = Field(min_length=3,max_length=10)


class ClusterApproveRequest(BaseModel):
    title: str = Field(min_length=1,max_length=300)
    content: str = Field(min_length=1,max_length=10000)
    source_versions: dict[UUID,str] = Field(min_length=3,max_length=10)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    memory_type: str | None = Field(default=None, min_length=1, max_length=80)
    since: date | None = None
    until: date | None = None

    @model_validator(mode='after')
    def ordered_dates(self):
        if self.since and self.until and self.since > self.until:
            raise ValueError('Start date must be on or before end date')
        return self


class AgentApprove(BaseModel):
    source_updated_at: dict[UUID, datetime] = Field(min_length=1, max_length=2)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, min_length=1, max_length=10000)


class CrossProjectSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5000)
    project_ids: list[UUID] = Field(min_length=1, max_length=20)
    limit: int = Field(default=20, ge=1, le=50)
    memory_type: str | None = None
    include_historical: bool = False

class ContextRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5000)
    max_chars: int = Field(default=6000, ge=500, le=16000)
    include_documents: bool = False


class ReflectRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    budget: Literal['quick', 'standard', 'deep'] = 'standard'
    include_documents: bool = False
    reasoning: bool = False
    as_of: datetime | None = None

    @model_validator(mode='after')
    def historical_scope(self):
        if self.as_of:
            if self.as_of.tzinfo is None:
                raise ValueError('Point-in-time answers need an explicit timezone')
            self.as_of = self.as_of.astimezone(timezone.utc)
            if self.as_of > datetime.now(timezone.utc):
                raise ValueError('Choose a point in the past')
            if self.include_documents:
                raise ValueError('Document version history is unavailable; point-in-time answers use memories only')
        return self


class ReflectionQueries(BaseModel):
    model_config = ConfigDict(extra='forbid')
    queries: list[str] = Field(max_length=2)


class ReflectionCitation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: int = Field(strict=True, ge=1, le=20)
    quote: str = Field(min_length=12, max_length=400)


class ReflectionClaim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=800)
    citations: list[ReflectionCitation] = Field(min_length=1, max_length=3)


class KnowledgeGap(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['missing', 'conflicting']
    description: str = Field(min_length=1, max_length=500)
    next_question: str = Field(min_length=1, max_length=500)
    citations: list[ReflectionCitation] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def supported_conflict(self):
        if not self.description.strip() or not self.next_question.strip():
            raise ValueError('Describe the gap and a useful next question')
        if self.kind == 'conflicting' and len({c.source for c in self.citations}) < 2:
            raise ValueError('A conflict requires quotations from two distinct sources')
        return self


class ReflectionAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    claims: list[ReflectionClaim] = Field(max_length=6)
    insufficient: bool
    gaps: list[KnowledgeGap] = Field(default_factory=list, max_length=3)


class BriefSource(BaseModel):
    id: UUID | int
    kind: Literal['memory', 'document_chunk'] = 'memory'
    version: str = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def source_identity(self):
        if (self.kind == 'memory' and not isinstance(self.id, UUID)) or (self.kind == 'document_chunk' and (type(self.id) is not int or self.id < 1)):
            raise ValueError('Invalid source ID for source kind')
        return self


class BriefCreate(ReflectRequest):
    title: str = Field(min_length=1, max_length=120)
    project_revision: str = Field(pattern=r'^[a-f0-9]{32}$')
    sources: list[BriefSource] = Field(min_length=1, max_length=20)
    claims: list[ReflectionClaim] = Field(min_length=1, max_length=6)
    refresh_of: UUID | None = None
    gaps: list[KnowledgeGap] = Field(default_factory=list, max_length=3)


class ConflictCompareRequest(BaseModel):
    first_id: str
    second_id: str


class ConflictResolveRequest(ConflictCompareRequest):
    current_id: str
    reason: str = Field(min_length=10, max_length=1000)


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


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=63)


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


class AgentScheduleUpdate(BaseModel):
    enabled: bool
    interval_hours: int = Field(default=24, ge=24, le=720)


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
