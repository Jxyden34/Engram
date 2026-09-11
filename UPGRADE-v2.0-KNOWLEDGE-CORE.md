# MemoryBank v2.0 — Knowledge Core

Upgrades v1.4 in place. Existing memories, documents, imports, MinIO data, API keys and audit history are preserved.

## Adds
- Entity Graph + relationships
- local Qwen enrichment of memories into entities/relations/events
- temporal `valid_from` / `valid_to`
- supersession chains
- dynamic memory score: importance × confidence × source trust × freshness × usage × temporal state
- Event Timeline
- Memory Health dashboard

## Install
```bash
cd /opt/memorybank
sudo unzip -o /home/jayden/memorybank-v2.0-knowledge-core-patch.zip -d /opt/memorybank
cd /opt/memorybank/memorybank
```

## Migrate
```bash
sudo docker compose exec -T db sh -lc \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < db/migrations/004_knowledge_core.sql
```

Verify:
```bash
sudo docker compose exec db sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\\dt entities" -c "\\dt entity_relations" -c "\\dt events" -c "\\dt knowledge_enrichment"'
```

## Rebuild
```bash
sudo docker compose build --no-cache api worker web
sudo docker compose up -d --force-recreate api worker web gateway
```

## Verify routes
```bash
sudo docker compose exec api python -c \
'from app.main import app; print([r.path for r in app.routes if any(x in getattr(r,"path","") for x in ["knowledge","timeline","health","supersede"])])'
```

## Populate the graph
Open **Knowledge Graph** and click **Enrich all memories**.

Watch the local Qwen jobs:
```bash
sudo docker compose logs -f worker
```

New pages:
```text
/knowledge
/timeline
/health
```

Use **Supersede** on a memory when a fact changes. The old fact becomes historical rather than being deleted.
