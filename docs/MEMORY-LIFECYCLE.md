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
