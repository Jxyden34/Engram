-- Alpha1: human-approved related links and reviewed consolidation captures.
ALTER TABLE agent_proposals DROP CONSTRAINT IF EXISTS agent_proposals_proposal_type_check;
ALTER TABLE agent_proposals ADD CONSTRAINT agent_proposals_proposal_type_check
  CHECK (proposal_type IN ('duplicate', 'conflict', 'stale', 'missing_provenance', 'related'));
ALTER TABLE agent_proposals DROP CONSTRAINT IF EXISTS agent_proposals_status_check;
ALTER TABLE agent_proposals ADD CONSTRAINT agent_proposals_status_check
  CHECK (status IN ('pending', 'dismissed', 'accepted'));
ALTER TABLE agent_proposals ADD COLUMN IF NOT EXISTS result_memory_id uuid REFERENCES memories(id);
