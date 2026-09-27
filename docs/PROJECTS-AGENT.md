# Engram Projects and Memory Agent development beta

Version: `2.7.0-dev-beta.1`.

## Projects

The migration creates a `Personal` project and assigns existing knowledge records to it. The web sidebar selects a project for the current browser. Search, memories, documents, imports, graph, timeline, connectors, captures and their background jobs use that project. API keys are bound to the project selected when created; a different `X-Engram-Project` header is rejected. Existing keys remain bound to Personal. OAuth MCP consent displays the selected project and binds the authorization code, access token, and refresh token to it. Renewing a token cannot switch projects. Existing OAuth grants remain bound to Personal.

Administrators can create and use projects at `/projects` or `POST /api/v1/projects`. New browser sessions default to Personal. Non-administrator sessions remain in Personal in this beta. API callers can supply `X-Engram-Project: <project UUID>`; the selected project must match their credential or administrator session. Project records are not automatically copied into new projects.

Administrators can explicitly select up to 20 projects on `/projects` and search memories across them. Each project is searched within its own row-level security context, and results show the source project. API keys and OAuth grants cannot use this cross-project endpoint. Opening a result switches the browser to its source project. Search uses the same embedding and ranking as single-project memory search; it does not include document chunks.

The migration enables and forces PostgreSQL row-level security on knowledge tables. Application database connections switch to the `engram_runtime` role so the policy applies even when the bootstrap database account is a superuser. Direct database maintenance by a superuser is outside the application boundary.

## Memory Agent

Use `/agent` to scan the selected project. The scan proposes review of high-similarity memories, pending ChatGPT and document import conflicts, facts not updated for two years, memories with confidence below 0.5, and imported memories without a source reference. Proposals link to the source memory and can be dismissed. The agent does not accept candidates, edit, merge or delete memories. Similarity, age and confidence are review hints, not proof that a memory is wrong.

An administrator can enable automatic scans for each project at `/agent`. They are off by default and run daily, every three days, or weekly through the existing worker queue. The first automatic scan is due after the chosen interval; use the manual button to scan now. Recent manual and automatic runs show completion, proposal counts, or errors. A failed queue submission is recorded as a failed run; the administrator can retry manually.

For a duplicate proposal, `Draft consolidation` asks the configured local AI model for a possible combined memory or a reason to keep the pair separate. The draft is saved with the proposal for human review and can be copied. If either source memory changes, the page marks the draft stale and disables copying until a new draft is generated. It never creates, updates, merges, or deletes a memory. The reviewer must check both source memories before using any draft.

## Upgrade and verification

1. Back up PostgreSQL and MinIO, then stop the API, worker and connector scheduler.
2. Apply `db/migrations/009_projects_agent.sql`, then `db/migrations/010_project_oauth.sql`, then `db/migrations/011_agent_schedules.sql`, using `psql -v ON_ERROR_STOP=1` before starting the updated API. A database already running beta migrations 009 and 010 only needs 011.
3. Rebuild the API, worker, connector scheduler and web images.
4. Verify that existing records appear in Personal, create a second project, add a memory there, and check it is absent from Personal search and MCP/API key access. Authorize an OAuth MCP client in the second project, renew its token, and verify both tokens remain there; an old grant should remain in Personal.
5. Run an agent scan in each project and verify proposals and run history stay in their project. Enable a schedule, force a due scan in preprod, and verify the worker completes it without changing memories.
6. Search across selected projects as an administrator and verify API keys cannot cross search. Generate a duplicate consolidation draft and verify both source memories remain unchanged.
7. Resume ingestion and check a connector sync and document import in a non-default project.

Do not deploy this beta to the production host before its migration, isolation tests, restore test and connector callback flow have passed. Keep the pre-upgrade backup for rollback; rolling back code alone after adding project-specific data would hide that data from older code.
