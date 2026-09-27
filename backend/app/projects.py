import re
from uuid import UUID

from fastapi import HTTPException

from app.database import DEFAULT_PROJECT_ID, connect, project_scope
from app.embeddings import embed_literal
from app import memories
from app.security import Principal


def list_projects(principal: Principal) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT p.id, p.slug, p.name, p.created_at
               FROM projects p
               WHERE %s OR p.id=%s
               ORDER BY p.created_at, p.name""",
            (principal.is_admin and principal.auth_type == "session", principal.project_id or DEFAULT_PROJECT_ID),
        ).fetchall()
    return [dict(row) for row in rows]


def resolve_project(principal: Principal, requested_id: str | None) -> str:
    if principal.auth_type != "session":
        bound = principal.project_id or DEFAULT_PROJECT_ID
        if requested_id and requested_id != bound:
            raise HTTPException(status_code=403, detail="Credential is bound to another project")
        return bound
    selected = requested_id or DEFAULT_PROJECT_ID
    try:
        UUID(selected)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid project ID") from None
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM projects WHERE id=%s AND (%s OR id=%s)",
            (selected, principal.is_admin, DEFAULT_PROJECT_ID),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return str(row["id"])


def create_project(name: str, slug: str, principal: Principal) -> dict:
    if not principal.is_admin or principal.auth_type != "session":
        raise HTTPException(status_code=403, detail="Administrator session required")
    slug = slug.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", slug):
        raise HTTPException(status_code=422, detail="Invalid project slug")
    with connect() as conn:
        if conn.execute("SELECT 1 FROM projects WHERE slug=%s", (slug,)).fetchone():
            raise HTTPException(status_code=409, detail="Project slug already exists")
        row = conn.execute(
            "INSERT INTO projects(slug,name,created_by) VALUES (%s,%s,%s) RETURNING id,slug,name,created_at",
            (slug, name.strip(), principal.user_id),
        ).fetchone()
        conn.commit()
    return dict(row)


def search_across(principal: Principal, project_ids: list[str], query: str,
                  limit: int, memory_type: str | None, include_historical: bool) -> list[dict]:
    if not principal.is_admin or principal.auth_type != "session":
        raise HTTPException(status_code=403, detail="Administrator session required")
    selected = list(dict.fromkeys(project_ids))
    if not selected or len(selected) > 20:
        raise HTTPException(status_code=422, detail="Select 1 to 20 projects")
    with connect() as conn:
        rows = conn.execute("SELECT id,name FROM projects WHERE id=ANY(%s::uuid[])",
                            (selected,)).fetchall()
    names = {str(row["id"]): row["name"] for row in rows}
    if len(names) != len(selected):
        raise HTTPException(status_code=404, detail="Project not found")
    vector = embed_literal(query)
    results = []
    for project_id in selected:
        with project_scope(project_id):
            for item in memories.search(query, limit, memory_type, include_historical, vector):
                item["project_id"] = project_id
                item["project_name"] = names[project_id]
                item["search_score"] = (
                    item["semantic_score"] * .72
                    + min(item["lexical_score"], 1.0) * .13
                    + item["memory_score"] * .15
                )
                results.append(item)
    results.sort(key=lambda item: item["search_score"], reverse=True)
    return results[:limit]
