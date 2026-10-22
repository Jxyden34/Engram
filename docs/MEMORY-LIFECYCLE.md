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
