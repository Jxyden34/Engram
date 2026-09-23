# Projects and Memory Agent development beta

Version: `2.7.0-dev-beta.1`.

## Projects

The migration creates a `Personal` project and assigns existing knowledge records to it. The web sidebar selects a project for the current browser. Search, memories, documents, imports, graph, timeline, connectors, captures and their background jobs use that project. API keys are bound to the project selected when created; a different `X-MemoryBank-Project` header is rejected. Existing keys remain bound to Personal. Existing OAuth MCP grants remain bound to Personal in this beta.

Administrators can create and use projects at `/projects` or `POST /api/v1/projects`. New browser sessions default to Personal. Non-administrator sessions remain in Personal in this beta. API callers can supply `X-MemoryBank-Project: <project UUID>`; the selected project must match their credential or administrator session. Project records are not automatically copied into new projects.

The migration enables and forces PostgreSQL row-level security on knowledge tables. Application database connections switch to the `memorybank_runtime` role so the policy applies even when the bootstrap database account is a superuser. Direct database maintenance by a superuser is outside the application boundary.

## Memory Agent

Use `/agent` to scan the selected project. The scan proposes review of high-similarity memories, pending imported conflicts, facts not updated for two years, and imported memories without a source reference. Proposals link to the source memory and can be dismissed. The agent does not accept candidates, edit, merge or delete memories. Similarity and age are review hints, not proof that a memory is wrong.

## Upgrade and verification

1. Back up PostgreSQL and MinIO, then stop the API, worker and connector scheduler.
2. Apply `db/migrations/009_projects_agent.sql` once using `psql -v ON_ERROR_STOP=1` before starting the updated API.
3. Rebuild the API, worker, connector scheduler and web images.
4. Verify that existing records appear in Personal, create a second project, add a memory there, and check it is absent from Personal search and MCP/API key access.
5. Run an agent scan in each project and verify proposals stay in their project.
6. Resume ingestion and check a connector sync and document import in a non-default project.

Do not deploy this beta to the production host before its migration, isolation tests, restore test and connector callback flow have passed. Keep the pre-upgrade backup for rollback; rolling back code alone after adding project-specific data would hide that data from older code.
