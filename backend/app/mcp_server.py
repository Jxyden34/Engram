from contextvars import ContextVar

from mcp.server import MCPServer

from app import memories
from app.documents import search_chunks
from app.security import Principal


mcp_principal: ContextVar[Principal | None] = ContextVar("mcp_principal", default=None)

mcp = MCPServer(
    "Personal Memory Bank",
    version="2.7.0-dev-beta.1",
    instructions=(
        "Search and maintain the user's private self-hosted memory bank. "
        "Use search before creating duplicate memories. "
        "Deletion is request-only and always requires human approval."
    ),
)


def principal(scope: str) -> Principal:
    value = mcp_principal.get()
    if not value:
        raise PermissionError("Unauthenticated MCP request")
    if scope not in value.scopes:
        raise PermissionError(f"Missing scope: {scope}")
    return value


@mcp.tool()
def memory_search(query: str, limit: int = 10, memory_type: str | None = None) -> list[dict]:
    """Search active memories by semantic meaning and text."""
    principal("memory:read")
    return memories.search(query, max(1, min(limit, 50)), memory_type)


@mcp.tool()
def document_search(query: str, limit: int = 8) -> list[dict]:
    """Search text extracted from uploaded documents."""
    principal("document:read")
    return search_chunks(query, max(1, min(limit, 30)))


@mcp.tool()
def memory_get(memory_id: str) -> dict:
    """Retrieve one memory by UUID."""
    principal("memory:read")
    return memories.get(memory_id)


@mcp.tool()
def memory_add(
    title: str,
    content: str,
    memory_type: str = "general",
    importance: int = 5,
    confidence: float = 1.0,
    tags: list[str] | None = None,
    source_ref: str | None = None,
) -> dict:
    """Create a memory. Prefer explicit facts over speculative inference."""
    p = principal("memory:write")
    return memories.create(
        {
            "title": title,
            "content": content,
            "memory_type": memory_type,
            "importance": importance,
            "confidence": confidence,
            "tags": tags or [],
            "source_type": "ai",
            "source_ref": source_ref,
            "metadata": {},
        },
        p.actor,
        p.user_id,
    )


@mcp.tool()
def memory_update(
    memory_id: str,
    title: str | None = None,
    content: str | None = None,
    memory_type: str | None = None,
    importance: int | None = None,
    confidence: float | None = None,
    tags: list[str] | None = None,
    reason: str | None = None,
) -> dict:
    """Update a memory while preserving a version in history."""
    p = principal("memory:write")
    changes = {
        key: value
        for key, value in {
            "title": title,
            "content": content,
            "memory_type": memory_type,
            "importance": importance,
            "confidence": confidence,
            "tags": tags,
            "reason": reason,
        }.items()
        if value is not None
    }
    row, _, _ = memories.update(memory_id, changes, p.actor)
    return row


@mcp.tool()
def memory_request_delete(memory_id: str, reason: str) -> dict:
    """Request soft deletion. This cannot approve or permanently erase data."""
    p = principal("memory:delete_request")
    row, _ = memories.request_delete(memory_id, p.actor, reason)
    return row


@mcp.tool()
def memory_relations(memory_id: str) -> list[dict]:
    """Return links between a memory and related memories."""
    principal("memory:read")
    return memories.relations(memory_id)
