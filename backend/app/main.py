from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from urllib.parse import quote
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from mcp.server.transport_security import TransportSecuritySettings

from app import memories
from app import health
from app import knowledge
from app import connectors
from app import oauth
from app import disaster_recovery as dr
from app import projects
from app import memory_agent
from app import document_memory_import as doc_mem
from app.audit import log
from app.capture import create_capture
from app.chatgpt_import import (
    accept_candidate,
    accept_safe_candidates,
    candidate_stats,
    create_import_job,
    list_candidates,
    list_eligible_documents,
    list_jobs,
    reject_candidate,
    update_candidate,
)
from app.config import settings
from app.database import connect, current_project_id, project_scope
from app.documents import bulk_upload, get_document, list_documents, minio_client, search_chunks, upload
from app.mcp_server import mcp, mcp_principal
from app.rate_limit import check_rate
from app.schemas import (
    ApiKeyCreate,
    CandidateUpdate,
    CaptureCreate,
    ChatImportCreate,
    ConnectorCreate,
    ConnectorUpdate,
    GmailOAuthStart,
    DeleteRequest,
    LoginRequest,
    MemoryCreate,
    MemorySupersede,
    EntityCreate,
    EventCreate,
    MemoryUpdate,
    OAuthClientCreate,
    OAuthClientUpdate,
    ProjectCreate,
    RejectRequest,
    RelationCreate,
    SearchRequest,
    SafeAcceptRequest,
)
from app.security import (
    ADMIN_SCOPES,
    CSRF_COOKIE,
    SESSION_COOKIE,
    api_key_principal,
    bearer_principal,
    authenticate,
    create_session,
    generate_api_key,
    require,
    sha256,
    revoke_session,
    session_principal,
    validate_csrf,
    validate_csrf_value,
    verify_password,
)


cfg = settings()

security = TransportSecuritySettings(
    allowed_hosts=[cfg.public_host, f"{cfg.public_host}:*", "localhost", "localhost:*", "127.0.0.1:*"],
    allowed_origins=[cfg.public_origin],
)
mcp_app = mcp.streamable_http_app(
    json_response=True,
    stateless_http=True,
    transport_security=security,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Engram API",
    version="2.7.0-dev-beta.1",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[cfg.public_origin],
    allow_origin_regex=r"^chrome-extension://[a-z]{32}$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Engram-Project", "Mcp-*", "Last-Event-ID"],
    expose_headers=["Mcp-Session-Id", "WWW-Authenticate"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/v1/"):
        check_rate(request, "api", 240, 60)

    if path.startswith("/api/v1/auth/login"):
        check_rate(request, "login", 12, 300)

    if path.startswith("/api/v1/") and path != "/api/v1/auth/login":
        try:
            validate_csrf(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    if path.startswith("/oauth/"):
        check_rate(request, "oauth", 120, 60)

    token = None
    selected_project = None
    if path.startswith("/api/v1/") and path not in {
        "/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/auth/me", "/api/v1/projects"
    }:
        try:
            selected_project = projects.resolve_project(
                authenticate(request), request.headers.get("x-engram-project") or request.cookies.get("engram_project")
            )
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if path == "/mcp" or path.startswith("/mcp/"):
        resource_metadata = oauth.protected_resource_metadata_url()
        base_scope = "mcp:use memory:read document:read"
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "OAuth Bearer token or API key required for MCP"},
                headers={
                    "WWW-Authenticate": (
                        f'Bearer resource_metadata="{resource_metadata}", '
                        f'scope="{base_scope}"'
                    )
                },
            )

        p = bearer_principal(auth[7:].strip(), oauth.mcp_resource())
        if not p:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired MCP token"},
                headers={
                    "WWW-Authenticate": (
                        'Bearer error="invalid_token", '
                        f'resource_metadata="{resource_metadata}", '
                        f'scope="{base_scope}"'
                    )
                },
            )

        required = {"mcp:use"}
        if request.headers.get("Mcp-Method", "").lower() == "tools/call":
            tool_scope = {
                "memory_search": "memory:read",
                "memory_get": "memory:read",
                "memory_relations": "memory:read",
                "document_search": "document:read",
                "memory_add": "memory:write",
                "memory_update": "memory:write",
                "memory_request_delete": "memory:delete_request",
            }.get(request.headers.get("Mcp-Name", ""))
            if tool_scope:
                required.add(tool_scope)

        missing = sorted(required - p.scopes)
        if missing:
            wanted = " ".join(sorted(required))
            return JSONResponse(
                status_code=403,
                content={"detail": f"Missing MCP scope(s): {', '.join(missing)}"},
                headers={
                    "WWW-Authenticate": (
                        'Bearer error="insufficient_scope", '
                        f'scope="{wanted}", '
                        f'resource_metadata="{resource_metadata}"'
                    )
                },
            )
        try:
            selected_project = projects.resolve_project(p, request.headers.get("x-engram-project"))
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        token = mcp_principal.set(p)

    try:
        with project_scope(selected_project or current_project_id()):
            return await call_next(request)
    finally:
        if token is not None:
            mcp_principal.reset(token)


@app.get("/health")
def health():
    return {"status": "ok", "service": "engram", "version": "2.7.0-dev-beta.1"}


@app.post("/api/v1/auth/login")
def login(body: LoginRequest, request: Request, response: Response):
    with connect() as conn:
        user = conn.execute(
            """
            SELECT id, username, display_name, password_hash, is_admin, is_active
            FROM users WHERE lower(username)=lower(%s)
            """,
            (body.username,),
        ).fetchone()

    if not user or not user["is_active"] or not verify_password(user["password_hash"], body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    session_token, csrf_token = create_session(str(user["id"]), request)
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        httponly=True,
        secure=cfg.cookie_secure,
        samesite="lax",
        max_age=cfg.session_ttl_hours * 3600,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=cfg.cookie_secure,
        samesite="lax",
        max_age=cfg.session_ttl_hours * 3600,
        path="/",
    )

    with connect() as conn:
        conn.execute("UPDATE users SET last_login_at=now() WHERE id=%s", (user["id"],))
        conn.commit()

    log(f"user:{user['username']}", "login", "session", request=request)
    return {
        "id": str(user["id"]),
        "username": user["username"],
        "display_name": user["display_name"],
        "is_admin": user["is_admin"],
    }


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response):
    p = authenticate(request)
    revoke_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    log(p.actor, "logout", "session", request=request)
    return {"ok": True}


@app.get("/api/v1/auth/me")
def me(request: Request):
    p = authenticate(request)
    return {
        "actor": p.actor,
        "user_id": p.user_id,
        "username": p.username,
        "is_admin": p.is_admin,
        "scopes": sorted(p.scopes),
        "project_id": current_project_id(),
    }


@app.get("/api/v1/projects")
def project_list(request: Request):
    return projects.list_projects(require(request, "memory:read"))


@app.post("/api/v1/projects", status_code=201)
def project_create(body: ProjectCreate, request: Request):
    p = require(request, "memory:write")
    row = projects.create_project(body.name, body.slug, p)
    log(p.actor, "project.created", "project", str(row["id"]), request, new_data=row)
    return row


@app.get("/api/v1/agent/proposals")
def agent_proposals(request: Request, status: str = "pending", limit: int = 100):
    require(request, "memory:read")
    return memory_agent.list_proposals(status, limit)


@app.post("/api/v1/agent/scan")
def agent_scan(request: Request):
    p = require(request, "memory:write")
    result = memory_agent.scan()
    log(p.actor, "agent.scan", "project", current_project_id(), request, new_data=result)
    return result


@app.post("/api/v1/agent/proposals/{proposal_id}/dismiss")
def agent_dismiss(proposal_id: str, request: Request):
    p = require(request, "memory:write")
    row = memory_agent.dismiss(proposal_id, p.actor)
    log(p.actor, "agent.proposal_dismissed", "agent_proposal", proposal_id, request)
    return row


@app.get("/api/v1/stats")
def stats(request: Request):
    require(request, "memory:read")
    with connect() as conn:
        return {
            "memories": conn.execute("SELECT count(*) AS n FROM memories WHERE deleted_at IS NULL AND (valid_to IS NULL OR valid_to > now())").fetchone()["n"],
            "entities": conn.execute("SELECT count(*) AS n FROM entities").fetchone()["n"],
            "events": conn.execute("SELECT count(*) AS n FROM events").fetchone()["n"],
            "documents": conn.execute("SELECT count(*) AS n FROM documents WHERE deleted_at IS NULL").fetchone()["n"],
            "pending_deletions": conn.execute("SELECT count(*) AS n FROM deletion_requests WHERE status='pending'").fetchone()["n"],
            "api_keys": conn.execute("SELECT count(*) AS n FROM api_keys WHERE revoked_at IS NULL AND project_id=%s", (current_project_id(),)).fetchone()["n"],
            "types": [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT memory_type, count(*) AS count
                    FROM memories
                    WHERE deleted_at IS NULL
                    GROUP BY memory_type
                    ORDER BY count(*) DESC
                    LIMIT 12
                    """
                ).fetchall()
            ],
            "recent": [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, title, memory_type, importance, updated_at
                    FROM memories
                    WHERE deleted_at IS NULL
                    ORDER BY updated_at DESC
                    LIMIT 8
                    """
                ).fetchall()
            ],
        }


@app.get("/api/v1/memories")
def memory_list(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    memory_type: str | None = None,
    tag: str | None = None,
    include_deleted: bool = False,
    include_historical: bool = False,
):
    p = require(request, "memory:read")
    if include_deleted and not p.is_admin:
        raise HTTPException(status_code=403, detail="Admin required for trash")
    return memories.list_memories(
        min(max(limit, 1), 100),
        max(offset, 0),
        memory_type,
        tag,
        include_deleted,
        include_historical,
    )


@app.post("/api/v1/memories", status_code=201)
def memory_create(body: MemoryCreate, request: Request):
    p = require(request, "memory:write")
    row = memories.create(body.model_dump(), p.actor, p.user_id)
    log(p.actor, "memory.created", "memory", str(row["id"]), request, new_data=row)
    return row


@app.get("/api/v1/memories/{memory_id}")
def memory_get(memory_id: str, request: Request):
    require(request, "memory:read")
    return memories.get(memory_id)


@app.patch("/api/v1/memories/{memory_id}")
def memory_update(memory_id: str, body: MemoryUpdate, request: Request):
    p = require(request, "memory:write")
    row, old, reason = memories.update(memory_id, body.model_dump(exclude_unset=True), p.actor)
    log(p.actor, "memory.updated", "memory", memory_id, request, reason, old, row)
    return row


@app.post("/api/v1/memories/{memory_id}/supersede", status_code=201)
def memory_supersede(memory_id: str, body: MemorySupersede, request: Request):
    p = require(request, "memory:write")
    row, old = memories.supersede(memory_id, body.model_dump(exclude_unset=True), p.actor, p.user_id)
    log(p.actor, "memory.superseded", "memory", memory_id, request, body.reason, old, row)
    return row


@app.get("/api/v1/memories/{memory_id}/versions")
def memory_versions(memory_id: str, request: Request):
    require(request, "memory:read")
    return memories.versions(memory_id)


@app.get("/api/v1/memories/{memory_id}/relations")
def memory_relations(memory_id: str, request: Request):
    require(request, "memory:read")
    return memories.relations(memory_id)


@app.post("/api/v1/memories/{memory_id}/relations")
def relation_create(memory_id: str, body: RelationCreate, request: Request):
    p = require(request, "memory:write")
    row = memories.add_relation(memory_id, body.target_memory_id, body.relation_type, p.actor)
    log(p.actor, "relation.created", "memory_relation", str(row["id"]), request, new_data=row)
    return row


@app.post("/api/v1/search")
def search(body: SearchRequest, request: Request):
    require(request, "memory:read")
    results = memories.search(body.query, body.limit, body.memory_type, body.include_historical)
    if body.include_documents:
        p = authenticate(request)
        if "document:read" in p.scopes:
            results.extend(search_chunks(body.query, max(3, body.limit // 2)))
            results.sort(key=lambda item: item.get("semantic_score", 0), reverse=True)
            results = results[: body.limit]
    return results


@app.post("/api/v1/memories/{memory_id}/request-delete", status_code=202)
def request_delete(memory_id: str, body: DeleteRequest, request: Request):
    p = require(request, "memory:delete_request")
    row, old = memories.request_delete(memory_id, p.actor, body.reason)
    log(p.actor, "memory.deletion_requested", "memory", memory_id, request, body.reason, old_data=old)
    return row


@app.get("/api/v1/deletion-requests")
def deletion_requests(request: Request):
    require(request, "memory:delete_approve")
    return memories.list_delete_requests()


@app.post("/api/v1/deletion-requests/{request_id}/approve")
def approve_delete(request_id: str, request: Request):
    p = require(request, "memory:delete_approve")
    result, old, reason = memories.approve_delete(request_id, p.actor)
    log(p.actor, "memory.soft_deleted", "memory", result["memory_id"], request, reason, old_data=old)
    return result


@app.post("/api/v1/deletion-requests/{request_id}/reject")
def reject_delete(request_id: str, body: RejectRequest, request: Request):
    p = require(request, "memory:delete_approve")
    result = memories.reject_delete(request_id, p.actor, body.reason)
    log(p.actor, "memory.deletion_rejected", "memory", str(result["memory_id"]), request, body.reason)
    return result


@app.post("/api/v1/memories/{memory_id}/restore")
def restore_memory(memory_id: str, request: Request):
    p = require(request, "memory:delete_approve")
    row, old = memories.restore(memory_id, p.actor)
    log(p.actor, "memory.restored", "memory", memory_id, request, old_data=old, new_data=row)
    return row


@app.get("/api/v1/documents")
def documents_list(request: Request):
    require(request, "document:read")
    return list_documents()


@app.post("/api/v1/documents", status_code=202)
async def documents_upload(request: Request, file: UploadFile = File(...)):
    p = require(request, "document:write")
    row = await upload(file, p.actor, p.user_id)
    log(p.actor, "document.uploaded", "document", str(row["id"]), request, new_data=row)
    return row


@app.post("/api/v1/documents/bulk", status_code=202)
async def documents_bulk_upload(
    request: Request,
    files: list[UploadFile] = File(...),
):
    p = require(request, "document:write")
    result = await bulk_upload(files, p.actor, p.user_id)
    log(
        p.actor,
        "document.bulk_uploaded",
        "document_batch",
        request=request,
        new_data=result["summary"],
    )
    return result


@app.get("/api/v1/documents/{document_id}/download")
def document_download(document_id: str, request: Request):
    require(request, "document:read")
    doc = get_document(document_id)
    obj = minio_client().get_object(cfg.minio_bucket, doc["object_key"])

    def stream():
        try:
            for chunk in obj.stream(1024 * 1024):
                yield chunk
        finally:
            obj.close()
            obj.release_conn()

    return StreamingResponse(
        stream(),
        media_type=doc["content_type"] or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc["filename"].split("/")[-1]}"'},
    )


@app.get("/api/v1/imports/chatgpt/documents")
def chatgpt_eligible_documents(request: Request):
    require(request, "document:read")
    return list_eligible_documents()


@app.get("/api/v1/imports/chatgpt/jobs")
def chatgpt_jobs(request: Request):
    require(request, "memory:read")
    return list_jobs()


@app.post("/api/v1/imports/chatgpt/jobs", status_code=202)
def chatgpt_create_job(body: ChatImportCreate, request: Request):
    p = require(request, "memory:write", "document:read")
    row = create_import_job(body.source_document_id, p.actor, p.user_id)
    log(
        p.actor,
        "chatgpt_import.created",
        "chat_import_job",
        str(row["id"]),
        request,
        new_data={
            "source_document_id": body.source_document_id,
            "model_name": row.get("model_name"),
        },
    )
    return row


@app.get("/api/v1/imports/chatgpt/candidates/stats")
def chatgpt_candidate_stats(request: Request):
    require(request, "memory:read")
    return candidate_stats()


@app.get("/api/v1/imports/chatgpt/candidates")
def chatgpt_candidates(
    request: Request,
    status: str = "pending",
    comparison: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    require(request, "memory:read")
    if status not in {"pending", "accepted", "rejected"}:
        raise HTTPException(status_code=400, detail="Invalid candidate status")
    if comparison and comparison not in {"new", "duplicate", "related", "updates", "conflicts"}:
        raise HTTPException(status_code=400, detail="Invalid comparison")
    return list_candidates(
        status=status,
        comparison=comparison,
        limit=min(max(limit, 1), 500),
        offset=max(offset, 0),
    )


@app.patch("/api/v1/imports/chatgpt/candidates/{candidate_id}")
def chatgpt_candidate_update(candidate_id: str, body: CandidateUpdate, request: Request):
    p = require(request, "memory:write")
    row = update_candidate(candidate_id, body.model_dump(exclude_unset=True))
    log(
        p.actor,
        "candidate_memory.updated",
        "candidate_memory",
        candidate_id,
        request,
        new_data={
            "title": row.get("title"),
            "memory_type": row.get("memory_type"),
            "comparison": row.get("comparison"),
        },
    )
    return row


@app.post("/api/v1/imports/chatgpt/candidates/{candidate_id}/accept")
def chatgpt_candidate_accept(candidate_id: str, request: Request):
    p = require(request, "memory:write")
    memory = accept_candidate(candidate_id, p.actor)
    log(
        p.actor,
        "candidate_memory.accepted",
        "candidate_memory",
        candidate_id,
        request,
        new_data={"accepted_memory_id": str(memory["id"])},
    )
    return memory


@app.post("/api/v1/imports/chatgpt/candidates/{candidate_id}/reject")
def chatgpt_candidate_reject(candidate_id: str, request: Request):
    p = require(request, "memory:write")
    result = reject_candidate(candidate_id, p.actor)
    log(
        p.actor,
        "candidate_memory.rejected",
        "candidate_memory",
        candidate_id,
        request,
    )
    return result


@app.post("/api/v1/imports/chatgpt/candidates/accept-safe")
def chatgpt_accept_safe(body: SafeAcceptRequest, request: Request):
    p = require(request, "memory:write")
    result = accept_safe_candidates(p.actor, body.import_job_id)
    log(
        p.actor,
        "candidate_memory.accepted_safe_batch",
        "candidate_memory_batch",
        request=request,
        new_data={
            "import_job_id": body.import_job_id,
            "accepted": result["accepted"],
            "errors": len(result["errors"]),
        },
    )
    return result


@app.get("/api/v1/imports/documents/sources")
def document_memory_sources(request: Request):
    require(request, "document:read")
    return doc_mem.list_ready_documents()


@app.get("/api/v1/imports/documents/jobs")
def document_memory_jobs(request: Request):
    require(request, "memory:read")
    return doc_mem.list_jobs()


@app.post("/api/v1/imports/documents/jobs/{document_id}", status_code=202)
def document_memory_create_job(document_id: str, request: Request):
    p = require(request, "memory:write", "document:read")
    row = doc_mem.create_job(document_id, p.actor, p.user_id)
    log(p.actor, "document_memory_import.created", "document_memory_job", str(row["id"]), request)
    return row


@app.post("/api/v1/imports/documents/analyse-all", status_code=202)
def document_memory_analyse_all(request: Request):
    p = require(request, "memory:write", "document:read")
    result = doc_mem.create_jobs_for_all_ready(p.actor, p.user_id)
    log(
        p.actor,
        "document_memory_import.analyse_all",
        "document_memory_batch",
        request=request,
        new_data={
            "queued": result["queued"],
            "skipped": result["skipped"],
            "errors": result["errors"],
        },
    )
    return result


@app.get("/api/v1/imports/documents/candidates")
def document_memory_candidates(
    request: Request,
    status: str = "pending",
    comparison: str | None = None,
    limit: int = 300,
    offset: int = 0,
):
    require(request, "memory:read")
    if status not in {"pending", "accepted", "rejected"}:
        raise HTTPException(status_code=400, detail="Invalid candidate status")
    if comparison and comparison not in {"new", "duplicate", "related", "updates", "conflicts"}:
        raise HTTPException(status_code=400, detail="Invalid comparison")
    return doc_mem.list_candidates(
        status=status,
        comparison=comparison,
        limit=min(max(limit, 1), 500),
        offset=max(offset, 0),
    )


@app.patch("/api/v1/imports/documents/candidates/{candidate_id}")
def document_memory_candidate_update(
    candidate_id: str,
    body: CandidateUpdate,
    request: Request,
):
    p = require(request, "memory:write")
    row = doc_mem.update_candidate(candidate_id, body.model_dump(exclude_unset=True))
    log(p.actor, "document_candidate_memory.updated", "document_candidate_memory", candidate_id, request)
    return row


@app.post("/api/v1/imports/documents/candidates/{candidate_id}/accept")
def document_memory_candidate_accept(candidate_id: str, request: Request):
    p = require(request, "memory:write")
    memory = doc_mem.accept_candidate(candidate_id, p.actor)
    log(
        p.actor,
        "document_candidate_memory.accepted",
        "document_candidate_memory",
        candidate_id,
        request,
        new_data={"accepted_memory_id": str(memory["id"])},
    )
    return memory


@app.post("/api/v1/imports/documents/candidates/{candidate_id}/reject")
def document_memory_candidate_reject(candidate_id: str, request: Request):
    p = require(request, "memory:write")
    result = doc_mem.reject_candidate(candidate_id, p.actor)
    log(p.actor, "document_candidate_memory.rejected", "document_candidate_memory", candidate_id, request)
    return result


@app.post("/api/v1/imports/documents/candidates/accept-safe")
def document_memory_accept_safe(request: Request):
    p = require(request, "memory:write")
    result = doc_mem.accept_safe(p.actor)
    log(
        p.actor,
        "document_candidate_memory.accepted_safe_batch",
        "document_candidate_memory_batch",
        request=request,
        new_data={"accepted": result["accepted"], "errors": len(result["errors"])},
    )
    return result


@app.get("/api/v1/knowledge/graph")
def knowledge_graph(request: Request, limit: int = 60):
    require(request, "memory:read")
    return knowledge.graph(limit)


@app.get("/api/v1/knowledge/entities")
def knowledge_entities(request: Request, limit: int = 150):
    require(request, "memory:read")
    return knowledge.list_entities(limit)


@app.post("/api/v1/knowledge/entities", status_code=201)
def knowledge_entity_create(body: EntityCreate, request: Request):
    p = require(request, "memory:write")
    row = knowledge.create_entity(body.model_dump(), p.actor, p.user_id)
    log(p.actor, "entity.created", "entity", str(row["id"]), request, new_data=row)
    return row


@app.get("/api/v1/knowledge/entities/{entity_id}")
def knowledge_entity_get(entity_id: str, request: Request):
    require(request, "memory:read")
    return knowledge.get_entity(entity_id)


@app.post("/api/v1/knowledge/enrich-all", status_code=202)
def knowledge_enrich_all(request: Request):
    p = require(request, "memory:write")
    result = knowledge.queue_all(p.actor)
    log(p.actor, "knowledge.enrich_all", "knowledge", request=request, new_data=result)
    return result


@app.get("/api/v1/timeline/events")
def timeline_events(request: Request, limit: int = 300):
    require(request, "memory:read")
    return knowledge.list_events(limit)


@app.post("/api/v1/timeline/events", status_code=201)
def timeline_event_create(body: EventCreate, request: Request):
    p = require(request, "memory:write")
    row = knowledge.create_event(body.model_dump(), p.actor, p.user_id)
    log(p.actor, "event.created", "event", str(row["id"]), request, new_data=row)
    return row


@app.get("/api/v1/health/summary")
def memory_health(request: Request):
    require(request, "memory:read")
    return health.summary()


@app.get("/api/v1/connectors/capabilities")
def connector_capabilities(request: Request):
    require(request, "connector:admin")
    return connectors.capabilities()


@app.post("/api/v1/connectors/gmail/authorize")
def gmail_authorize(body: GmailOAuthStart, request: Request):
    principal = require(request, "connector:admin")
    session = request.cookies.get(SESSION_COOKIE)
    if principal.auth_type != "session" or not principal.user_id or not session:
        raise HTTPException(status_code=403, detail="Gmail authorization requires an administrator browser session")
    return {"authorization_url": connectors.start_gmail_oauth(
        body.model_dump(), principal.actor, principal.user_id, sha256(session)
    )}


@app.get("/api/v1/connectors/gmail/callback", include_in_schema=False)
def gmail_callback(request: Request):
    principal = require(request, "connector:admin")
    session = request.cookies.get(SESSION_COOKIE)
    if principal.auth_type != "session" or not principal.user_id or not session:
        raise HTTPException(status_code=403, detail="Return to Engram in the browser where Gmail setup started")
    state = request.query_params.get("state", "")
    session_hash = sha256(session)
    if request.query_params.get("error"):
        if state:
            connectors.cancel_gmail_oauth(state, session_hash)
        return RedirectResponse("/connectors?gmail=cancelled", status_code=303,
                                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    connector_id, email_address = connectors.finish_gmail_oauth(
        state, request.query_params.get("code", ""), session_hash
    )
    log(principal.actor, "connector.created", "connector", connector_id, request,
        new_data={"connector_type": "gmail", "email_address": email_address})
    return RedirectResponse("/connectors?gmail=connected", status_code=303,
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@app.get("/api/v1/connectors")
def connector_list(request: Request):
    require(request, "connector:admin")
    return connectors.list_connectors()


@app.post("/api/v1/connectors", status_code=201)
def connector_create(body: ConnectorCreate, request: Request):
    p = require(request, "connector:admin")
    row = connectors.create_connector(body.model_dump(), p.actor, p.user_id)
    log(
        p.actor,
        "connector.created",
        "connector",
        str(row["id"]),
        request,
        new_data={
            "name": row["name"],
            "connector_type": row["connector_type"],
            "schedule_minutes": row["schedule_minutes"],
        },
    )
    return row


@app.patch("/api/v1/connectors/{connector_id}")
def connector_update(connector_id: str, body: ConnectorUpdate, request: Request):
    p = require(request, "connector:admin")
    row = connectors.update_connector(
        connector_id,
        body.model_dump(exclude_unset=True),
    )
    log(
        p.actor,
        "connector.updated",
        "connector",
        connector_id,
        request,
        new_data={
            "name": row["name"],
            "enabled": row["enabled"],
            "schedule_minutes": row["schedule_minutes"],
        },
    )
    return row


@app.delete("/api/v1/connectors/{connector_id}")
def connector_delete(connector_id: str, request: Request):
    p = require(request, "connector:admin")
    row = connectors.delete_connector(connector_id)
    log(p.actor, "connector.deleted", "connector", connector_id, request)
    return row


@app.post("/api/v1/connectors/{connector_id}/sync", status_code=202)
def connector_sync(connector_id: str, request: Request):
    p = require(request, "connector:admin")
    run = connectors.queue_sync(connector_id)
    log(
        p.actor,
        "connector.sync_queued",
        "connector",
        connector_id,
        request,
        new_data={"run_id": str(run["id"])},
    )
    return run


@app.get("/api/v1/connectors/runs")
def connector_runs(request: Request, connector_id: str | None = None, limit: int = 100):
    require(request, "connector:admin")
    return connectors.list_runs(connector_id, min(max(limit, 1), 500))


@app.post("/api/v1/capture", status_code=202)
def browser_capture(body: CaptureCreate, request: Request):
    p = require(request, "capture:write")
    row = create_capture(body.model_dump(), p.actor, p.user_id)
    log(
        p.actor,
        "browser.capture",
        "browser_capture",
        str(row["id"]),
        request,
        new_data={
            "capture_type": row["capture_type"],
            "title": row["title"],
            "url": row["url"],
            "document_id": str(row["document_id"]),
        },
    )
    return row


@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
def oauth_resource_metadata():
    return oauth.protected_resource_metadata()


@app.get("/.well-known/oauth-authorization-server")
def oauth_server_metadata():
    return oauth.authorization_server_metadata()


@app.get("/oauth/authorize")
def oauth_authorize_get(request: Request):
    params = {key: value for key, value in request.query_params.items()}
    try:
        authorization = oauth.validate_authorization_request(params)
    except HTTPException as exc:
        # Redirect errors only after the client and redirect URI are known safely.
        client_id = params.get("client_id")
        redirect_uri = params.get("redirect_uri")
        if client_id and redirect_uri:
            try:
                oauth._load_client(client_id, redirect_uri)
                return oauth._redirect_with_params(
                    redirect_uri,
                    {
                        "error": "invalid_request",
                        "error_description": str(exc.detail),
                        "state": params.get("state"),
                        "iss": oauth.issuer(),
                    },
                )
            except HTTPException:
                pass
        raise

    session_token = request.cookies.get(SESSION_COOKIE)
    principal = session_principal(session_token) if session_token else None
    if not principal:
        return_to = request.url.path
        if request.url.query:
            return_to += "?" + request.url.query
        return RedirectResponse(
            "/login?returnTo=" + quote(return_to, safe=""),
            status_code=302,
        )

    csrf = request.cookies.get(CSRF_COOKIE, "")
    return oauth.render_consent(
        authorization,
        principal.username or principal.actor,
        csrf,
    )


@app.post("/oauth/authorize")
async def oauth_authorize_post(request: Request):
    form = await request.form()
    data = {key: str(value) for key, value in form.items()}

    session_token = request.cookies.get(SESSION_COOKIE)
    principal = session_principal(session_token) if session_token else None
    if not principal:
        raise HTTPException(status_code=401, detail="Login session required")

    validate_csrf_value(
        session_token,
        request.cookies.get(CSRF_COOKIE),
        data.get("csrf_token"),
    )

    authorization = oauth.validate_authorization_request(data)
    if data.get("decision") != "allow":
        return oauth._redirect_with_params(
            authorization["redirect_uri"],
            {
                "error": "access_denied",
                "state": authorization.get("state"),
                "iss": oauth.issuer(),
            },
        )

    code = oauth.create_authorization_code(
        authorization["client_id"],
        principal.user_id,
        authorization["redirect_uri"],
        authorization["scopes"],
        authorization["resource"],
        authorization["code_challenge"],
    )
    log(
        principal.actor,
        "oauth.authorized",
        "oauth_client",
        authorization["client_id"],
        request,
        new_data={
            "scopes": authorization["scopes"],
            "resource": authorization["resource"],
        },
    )
    return oauth._redirect_with_params(
        authorization["redirect_uri"],
        {
            "code": code,
            "state": authorization.get("state"),
            "iss": oauth.issuer(),
        },
    )


@app.post("/oauth/token")
async def oauth_token(request: Request):
    form_data = await request.form()
    form = {key: str(value) for key, value in form_data.items()}
    grant_type = form.get("grant_type")

    if grant_type == "authorization_code":
        return oauth.exchange_authorization_code(form)
    if grant_type == "refresh_token":
        return oauth.exchange_refresh_token(form)
    return oauth.oauth_error("unsupported_grant_type", "Only authorization_code and refresh_token are supported")


@app.post("/oauth/revoke")
async def oauth_revoke(request: Request):
    form_data = await request.form()
    return oauth.revoke_token({key: str(value) for key, value in form_data.items()})


@app.post("/oauth/register", status_code=201)
async def oauth_register(request: Request):
    if not cfg.oauth_dcr_enabled:
        raise HTTPException(status_code=404, detail="Dynamic client registration is disabled")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON client metadata required")
    return oauth.dynamic_register(body)


@app.get("/api/v1/oauth/summary")
def oauth_admin_summary(request: Request):
    require(request, "oauth:admin")
    return oauth.oauth_summary()


@app.get("/api/v1/oauth/clients")
def oauth_client_list(request: Request):
    require(request, "oauth:admin")
    return oauth.list_clients()


@app.post("/api/v1/oauth/clients", status_code=201)
def oauth_client_create(body: OAuthClientCreate, request: Request):
    p = require(request, "oauth:admin")
    row = oauth.create_static_client(
        body.client_name,
        body.redirect_uris,
        body.allowed_scopes,
        p.actor,
        p.user_id,
    )
    log(
        p.actor,
        "oauth.client_created",
        "oauth_client",
        row["client_id"],
        request,
        new_data={
            "client_name": row["client_name"],
            "redirect_uris": row["redirect_uris"],
            "allowed_scopes": row["allowed_scopes"],
        },
    )
    return row


@app.patch("/api/v1/oauth/clients/{client_id:path}")
def oauth_client_update(client_id: str, body: OAuthClientUpdate, request: Request):
    p = require(request, "oauth:admin")
    row = oauth.update_static_client(
        client_id,
        body.model_dump(exclude_unset=True),
    )
    log(
        p.actor,
        "oauth.client_updated",
        "oauth_client",
        client_id,
        request,
        new_data={
            "client_name": row["client_name"],
            "is_active": row["is_active"],
            "allowed_scopes": row["allowed_scopes"],
        },
    )
    return row


@app.delete("/api/v1/oauth/clients/{client_id:path}")
def oauth_client_revoke(client_id: str, request: Request):
    p = require(request, "oauth:admin")
    row = oauth.revoke_client(client_id)
    log(p.actor, "oauth.client_revoked", "oauth_client", client_id, request)
    return row


@app.get("/api/v1/oauth/grants")
def oauth_grant_list(request: Request):
    require(request, "oauth:admin")
    return oauth.list_consents()


@app.delete("/api/v1/oauth/grants/{consent_id}")
def oauth_grant_revoke(consent_id: str, request: Request):
    p = require(request, "oauth:admin")
    row = oauth.revoke_consent(consent_id)
    log(p.actor, "oauth.consent_revoked", "oauth_consent", consent_id, request)
    return row


@app.get("/api/v1/dr/summary")
def disaster_recovery_summary(request: Request):
    require(request, "dr:admin")
    return dr.summary()


@app.get("/api/v1/dr/artifacts")
def disaster_recovery_artifacts(request: Request, limit: int = 100):
    require(request, "dr:admin")
    return dr.artifacts(limit)


@app.get("/api/v1/dr/restore-tests")
def disaster_recovery_restore_tests(request: Request, limit: int = 50):
    require(request, "dr:admin")
    return dr.restore_tests(limit)


@app.get("/api/v1/dr/replication-runs")
def disaster_recovery_replication_runs(request: Request, limit: int = 50):
    require(request, "dr:admin")
    return dr.replication_runs(limit)


@app.get("/api/v1/dr/requests")
def disaster_recovery_requests(request: Request, limit: int = 30):
    require(request, "dr:admin")
    return dr.recent_requests(limit)


@app.post("/api/v1/dr/scan", status_code=202)
def disaster_recovery_scan(request: Request):
    p = require(request, "dr:admin")
    row = dr.queue_request("scan", p.actor)
    log(p.actor, "dr.scan_queued", "dr_request", str(row["id"]), request)
    return row


@app.post("/api/v1/dr/restore-test", status_code=202)
def disaster_recovery_restore_test(request: Request):
    p = require(request, "dr:admin")
    row = dr.queue_request("restore_test", p.actor)
    log(p.actor, "dr.restore_test_queued", "dr_request", str(row["id"]), request)
    return row


@app.post("/api/v1/dr/replicate", status_code=202)
def disaster_recovery_replicate(request: Request):
    p = require(request, "dr:admin")
    row = dr.queue_request("replicate", p.actor)
    log(p.actor, "dr.replication_queued", "dr_request", str(row["id"]), request)
    return row


@app.get("/api/v1/audit")
def audit_list(request: Request, limit: int = 100):
    require(request, "audit:read")
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, actor, action, entity_type, entity_id, ip_address, reason, created_at
            FROM audit_log
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (min(max(limit, 1), 500),),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/v1/keys")
def keys_list(request: Request):
    require(request, "keys:admin")
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, key_prefix, scopes, created_at, last_used_at, revoked_at
            FROM api_keys
            WHERE project_id=%s
            ORDER BY created_at DESC
            """,
            (current_project_id(),),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/v1/keys", status_code=201)
def key_create(body: ApiKeyCreate, request: Request):
    p = require(request, "keys:admin")
    allowed = set(ADMIN_SCOPES)
    unknown = set(body.scopes) - allowed
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown scopes: {sorted(unknown)}")
    token, prefix, digest = generate_api_key()
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO api_keys(owner_id, name, key_prefix, key_hash, scopes, project_id)
            VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING id, name, key_prefix, scopes, created_at
            """,
            (p.user_id, body.name, prefix, digest, body.scopes, current_project_id()),
        ).fetchone()
        conn.commit()
    result = dict(row)
    result["token"] = token
    result["warning"] = "Shown once. Store this token securely."
    log(p.actor, "api_key.created", "api_key", str(row["id"]), request, new_data={k: v for k, v in result.items() if k != "token"})
    return result


@app.delete("/api/v1/keys/{key_id}")
def key_revoke(key_id: str, request: Request):
    p = require(request, "keys:admin")
    with connect() as conn:
        row = conn.execute(
            """
            UPDATE api_keys SET revoked_at=now()
            WHERE id=%s AND project_id=%s AND revoked_at IS NULL
            RETURNING id, name, revoked_at
            """,
            (key_id, current_project_id()),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Active key not found")
        conn.commit()
    log(p.actor, "api_key.revoked", "api_key", key_id, request)
    return dict(row)


app.mount("/", mcp_app)
