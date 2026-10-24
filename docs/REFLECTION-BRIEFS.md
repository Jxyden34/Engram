# Reflection and project briefs — v2.8 development

Reflect brings together current memories to answer a question with multiple
supporting excerpts. Saved project briefs are reviewed snapshots of these answers,
inspired by Hindsight's Reflect and mental models. Engram remains the memory store;
the feature uses its hybrid retriever, local Ollama and project isolation.

The server prerelease track begins at **2.8.0-pre.1**. Stable remains v2.7.0;
native update channels and production deployment are unchanged. See
[prerelease qualification](V2.8-PRERELEASES.md) for the stable-promotion gate.

## Use

Open **Intelligence → Reflect & project briefs** in the active project. Enter a
question and choose an evidence budget:

| Budget | Maximum retrieved memories | Maximum source content characters |
| --- | ---: | ---: |
| Quick | 6 | 4,000 |
| Standard | 12 | 9,000 |
| Deep | 20 | 16,000 |

Each excerpt is capped at 1,600 characters. These are evidence limits, not total
prompt/token limits. Titles, provenance, dates and instructions add prompt overhead.
Deep expands evidence; it does not run an autonomous agent or exhaustive scan.

Review each claim and its source quotes before **Save reviewed brief**. A saved
brief returns without regenerating an answer. Opening it checks freshness against
the active project's current memories. Any added/edited/deleted current memory
conservatively marks the snapshot **needs review**, even if unrelated. An expired
or future-dated source is unavailable. If supporting evidence changed or became
unavailable, prior claims and quotes are withheld. Rebuild generates a new preview;
save creates a new snapshot, leaving existing briefs and source memories unchanged.
Delete removes only the saved brief.

## API and permissions

- `POST /api/v1/intelligence/reflect`: `memory:read`; body
  `{"question":"What guides this project?","budget":"standard"}`. Rate limited to
  three requests per minute under the existing request limiter.
- `GET /api/v1/intelligence/briefs`: `memory:read`; newest 100 briefs.
- `GET /api/v1/intelligence/briefs/{id}`: `memory:read`; claims, evidence status,
  question, budget and freshness status.
- `POST /api/v1/intelligence/briefs`: `memory:write`; explicit title, question,
  budget, project revision, source IDs/version fingerprints and reviewed claims.
  Source numbers refer to their order in the submitted sources array. Use the
  returned reflection's source order and fingerprints; a source/version/revision
  mismatch returns 409. Rebuild instead of resubmitting stale output.
- `DELETE /api/v1/intelligence/briefs/{id}`: `memory:write`.

Normal session CSRF protections apply. API keys and OAuth credentials retain their
project binding. Brief creation/deletion is audited without copying generated
content into the audit event. The new table has forced row-level security.

## Validation and limits

Every generated claim must have one to three citations. Quotes must be exact,
12–400 character substrings of the numbered evidence. Invalid output returns 502;
unavailable model returns 503; memories changing during generation return 409.
An empty evidence set abstains without invoking the model. Historical and future
memories are excluded. Reflect does not search documents or other projects.

Exact quotes establish traceability, not proof that a generated interpretation is
correct. Review whether each excerpt supports the conclusion. Retrieved candidates
may be irrelevant, budgets may miss evidence, and conflicting facts still need
human review. Saved briefs are not injected back into retrieval or automatically
treated as verified facts. Automatic observations, background refresh, autonomous
query expansion and lifecycle decay/archival are outside this increment.

## Migration and rollout

Back up PostgreSQL before applying `db/migrations/013_project_briefs.sql` with
`psql -v ON_ERROR_STOP=1`, after migrations 009–012 and before the updated API/web.
Fresh Docker installations and CI initialize it automatically. Migration 013 is
idempotent and adds only a table, index, RLS policy and grants; existing memories
are unchanged. Run backend tests against an isolated database and build the web
app before promotion. Rollback can restore the previous API/web images and leave
the unused briefs table in place, preserving saved snapshots.
