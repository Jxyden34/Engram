-- Cluster drafts record exactly one reviewed result atomically in their snapshot.
GRANT UPDATE(snapshot) ON project_briefs TO engram_runtime;
