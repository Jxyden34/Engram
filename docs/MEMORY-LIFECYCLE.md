# Memory lifecycle prereleases

## Reviewed consolidation — pre.2

Open **Memory Agent**, scan the active project and choose **Draft consolidation**
on a duplicate pair. Read both sources and their exact supporting quotes, edit
the proposed title/text, check the review box and save. Similarity alone never
means two memories can safely be merged; unsafe AI drafts remain separate.

The new summary links to both originals with `derived_from` relations and records
their IDs and checked quotations. Its confidence and source trust do not exceed
the weaker source. Both originals remain unchanged and searchable. Repeating an
accepted approval returns the existing result instead of creating duplicates.
Changed, deleted, historical or future-dated source evidence blocks approval.
Older drafts without quotations must be regenerated before approval.

Quote matching verifies traceability, not semantic correctness. Human edits and
approval remain essential. Pairwise consolidation is the bounded first increment;
it does not automatically rewrite clusters or remove duplicate originals.

This increment reuses the existing Agent tables and requires no new migration.
All prereleases follow [the explicit stable-promotion gate](V2.8-PRERELEASES.md).

## Explainable retrieval decay — pre.3

Hybrid retrieval gradually reduces the priority of evidence older than 180 days.
Confidence, source trust and importance determine the strength; use in the last
180 days reduces the penalty. New facts have a grace period, and a qualifying
candidate's score never loses more than 35% through this adjustment. Low priority
is not deletion, archival, or proof that an old fact is false.

Search results expose `decay_factor`, `decay_reasons` and a match explanation,
also shown in Intelligence. Explicit history queries bypass this added penalty.
No background rewrite, database migration or automatic removal is involved.
The existing quality score remains in place. This is an explainable ranking
heuristic, not a trained estimate of truth or a guarantee that every old memory
appears within the bounded candidate pool.

## Searchable archival — pre.4

Open a memory, enter a reason and choose **Archive memory**. Its content, version
history and provenance remain intact. Archive and restore require `memory:write`,
are audited and reject stale edits. Restore from the same memory page.

Default memory lists, hybrid/legacy search, Ask, Reflect, context building and new
Agent suggestions exclude archived memories. The **Include archived** control in
Memories includes them in lists/search; REST search accepts `include_archived:true`
and MCP `memory_search` accepts the same flag. Direct memory links still work in
the authorized project. History and archive filters are independent; include both
when searching a memory that is both archived and historical. Archival does not
mean deletion, does not erase existing graph/history views, and is never automatic.

Archiving a supporting source marks its saved briefs for review and hides their
previous answer. Restoring does not silently recertify a previous brief.

Back up PostgreSQL and apply `014_memory_archival.sql` after 013 before updating
API/workers. Fresh installs/CI mount it automatically. Rollback may retain the
additive column and restore prior application images, but older versions do not
understand archival and may show archived memories in default retrieval. Preserve
the backup and test rollback in isolation before stable promotion.

## Brief refresh for review — pre.5

Open a saved project brief and choose **Refresh for review**. Engram reuses its
saved question and evidence budget to retrieve current, unarchived memories. It
does not feed the stale generated answer back to the model. The result is a
preview; explicitly **Save reviewed brief** to create a new snapshot. The original
snapshot remains unchanged and the refreshed brief links back to it.

`POST /api/v1/intelligence/briefs/{id}/refresh` requires `memory:read` and shares
Reflect's rate limit. Saving the reviewed result still requires `memory:write`,
valid current source fingerprints and the previous brief in the same project.
The save body includes `refresh_of`; its question/budget must match that parent.
Changing evidence before save returns 409. New refreshes are never automatically
saved or scheduled. Explicitly deleting a previous brief leaves a historical
reference in its descendants; their old-brief link then returns not found.

This increment uses existing snapshot metadata and needs no additional migration.
Background refresh and automatic observations remain outside this prerelease.

## Document-aware Reflect — pre.6

Choose **Include document evidence** to combine memories with indexed excerpts from
ready documents, including captured or connector documents. Excerpts retain their
document identity and checked quotes; the source links to its document entry.
`include_documents:true` requires `document:read` as well as the ordinary memory
scope, including when saving, opening or refreshing a document-backed brief.
Memory-only credentials cannot list or read these briefs. Source deletion or
chunk changes invalidate the saved answer. Documents are evidence, never commands.
This uses indexed text, not attachments that have not been imported/extracted.

## Brief comparisons — pre.7

Refresh previews and saved descendants show added, removed and unchanged answer
statements and sources whose fingerprints changed. Text comparison tolerates
whitespace/case changes; it does not infer semantic equivalence or prove a
contradiction. Removed text is explicitly historical, never new retrieval evidence.
Claims whose supporting sources are deleted, archived or inaccessible are redacted.
Document scope and project isolation apply to both snapshots. A deleted parent
produces an unavailable comparison, not a recreated or guessed previous answer.

## Bounded follow-up retrieval — pre.8

Enable **Allow bounded follow-up searches** with Standard or Deep evidence budgets.
After reading initial evidence, the local model may propose one additional search
for Standard or two for Deep. Quick keeps one search. Every retrieval uses the
same project and source permissions; repeated sources share one citation number
and the final source/character limits remain unchanged. The UI shows executed
queries and whether follow-up planning was unavailable. A failed or invalid plan
falls back to the retrieved evidence instead of claiming extra reasoning succeeded.
This is a bounded retrieval expansion, not an open-ended autonomous agent.

## Reviewed cluster consolidation — pre.9

In Memory Agent, choose 3–10 related current memories and draft a group summary.
Every selected source must have an exact supporting quote before a draft can be
saved. Review the quotes, edit the summary and explicitly approve it. The new
memory preserves all originals, has a `derived_from` link to every source, and
inherits no more confidence/trust than the weakest source. Approval locks the
draft and sources, checks their fingerprints and records one result for retries.
Deleted, archived, changed or foreign-project sources cannot be approved.

Cluster drafts use project-scoped evidence snapshots, are separate from ordinary
project briefs and never enter retrieval as facts until human approval. Showing
100 current memories bounds the picker; use search on the Memories page to inspect
larger collections. Apply migration `015_cluster_review.sql` after 014 before this
API; fresh installations and CI mount it automatically.

## Point-in-time answers — pre.10

Choose **What did I know then?** in Reflect. Engram reconstructs each eligible
memory from the first pre-change snapshot after that instant, or its unchanged
stored state. Creation/update times and factual validity must cover the requested
point. Current wording and future embeddings never substitute for historical
evidence; point-in-time retrieval uses lexical matching of versioned text.

Explicit timezone offsets are required by the API. The web picker uses local time
and sends UTC. Saved briefs retain their point in time and refresh against that
same point. Deleted/archived records remain unavailable; this feature does not
restore deleted information. Incomplete legacy snapshots without timestamps cannot
establish past knowledge. This reconstructs recorded history, not everything the
user knew outside Engram. Documents have no immutable version history here, so
document evidence and point-in-time mode cannot be combined. No new migration.

### pre.11 — Knowledge gaps
Reflect can report missing evidence or conflicts with checked quotations and a next question. Conflicts require two distinct cited sources. Stale supporting evidence hides saved gaps together with claims; gap questions run only when requested.


### pre.12 — Protect important memories
Explicit pin/unpin on memory details removes age penalties in both SQL quality scores and hybrid ranking. It does not bypass validity, archival, deletion, access or query relevance. Changes require memory:write and a current timestamp, retain a version and atomic audit event. Apply migration 016.

