from app.database import connect


def summary():
    with connect() as conn:
        total = int(conn.execute("SELECT count(*) AS n FROM memories WHERE deleted_at IS NULL").fetchone()["n"])
        current = int(conn.execute("SELECT count(*) AS n FROM memories WHERE deleted_at IS NULL AND (valid_to IS NULL OR valid_to > now())").fetchone()["n"])
        entities = int(conn.execute("SELECT count(*) AS n FROM entities").fetchone()["n"])
        relations = int(conn.execute("SELECT count(*) AS n FROM entity_relations").fetchone()["n"])
        events = int(conn.execute("SELECT count(*) AS n FROM events").fetchone()["n"])
        low = int(conn.execute("SELECT count(*) AS n FROM memories WHERE deleted_at IS NULL AND confidence < .60 AND (valid_to IS NULL OR valid_to > now())").fetchone()["n"])
        stale = int(conn.execute("SELECT count(*) AS n FROM memories WHERE deleted_at IS NULL AND (valid_to IS NULL OR valid_to > now()) AND updated_at < now()-interval '180 days' AND coalesce(last_accessed_at,updated_at) < now()-interval '90 days'").fetchone()["n"])
        orphan = int(conn.execute("SELECT count(*) AS n FROM memories m WHERE m.deleted_at IS NULL AND (m.valid_to IS NULL OR m.valid_to > now()) AND NOT EXISTS (SELECT 1 FROM memory_entity_links l WHERE l.memory_id=m.id)").fetchone()["n"])
        temporal = int(conn.execute("SELECT count(*) AS n FROM memories WHERE deleted_at IS NULL AND valid_from IS NOT NULL AND valid_to IS NOT NULL AND valid_from > valid_to").fetchone()["n"])
        conflicts = int(conn.execute("SELECT (SELECT count(*) FROM candidate_memories WHERE status='pending' AND comparison='conflicts') + (SELECT count(*) FROM document_candidate_memories WHERE status='pending' AND comparison='conflicts') AS n").fetchone()["n"])
        unenriched = int(conn.execute("SELECT count(*) AS n FROM memories m LEFT JOIN knowledge_enrichment k ON k.memory_id=m.id WHERE m.deleted_at IS NULL AND (m.valid_to IS NULL OR m.valid_to > now()) AND (k.memory_id IS NULL OR k.memory_updated_at<m.updated_at OR k.status='failed')").fetchone()["n"])
        duplicates = [dict(r) for r in conn.execute("""
          SELECT m.id AS memory_id,m.title,n.id AS duplicate_id,n.title AS duplicate_title,n.similarity
          FROM memories m CROSS JOIN LATERAL (
            SELECT m2.id,m2.title,1-(m2.embedding<=>m.embedding) AS similarity FROM memories m2
            WHERE m2.id<>m.id AND m2.deleted_at IS NULL AND (m2.valid_to IS NULL OR m2.valid_to>now()) AND m2.embedding IS NOT NULL
            ORDER BY m2.embedding<=>m.embedding LIMIT 1
          ) n
          WHERE m.deleted_at IS NULL AND (m.valid_to IS NULL OR m.valid_to>now()) AND m.embedding IS NOT NULL AND n.similarity>=.94 AND m.id::text<n.id::text
          ORDER BY n.similarity DESC LIMIT 30
        """).fetchall()]
        stale_items = [dict(r) for r in conn.execute("SELECT id,title,memory_type,updated_at FROM memories WHERE deleted_at IS NULL AND (valid_to IS NULL OR valid_to>now()) AND updated_at<now()-interval '180 days' AND coalesce(last_accessed_at,updated_at)<now()-interval '90 days' ORDER BY updated_at LIMIT 30").fetchall()]
    for x in duplicates: x["similarity"] = float(x["similarity"])
    denom=max(current,1)
    penalty=min(conflicts*4,20)+min(len(duplicates)*1.5,15)+min(low/denom*25,12)+min(stale/denom*22,12)+min(orphan/denom*18,10)+min(temporal*5,20)+min(unenriched/denom*20,11)
    score=max(0,min(100,round(100-penalty)))
    issues=[
      {"type":"conflicts","label":"Pending contradictions","count":conflicts,"severity":"high" if conflicts else "ok"},
      {"type":"duplicates","label":"Likely duplicate pairs","count":len(duplicates),"severity":"medium" if duplicates else "ok"},
      {"type":"low","label":"Low-confidence memories","count":low,"severity":"medium" if low else "ok"},
      {"type":"stale","label":"Potentially stale memories","count":stale,"severity":"medium" if stale else "ok"},
      {"type":"orphan","label":"Memories not linked to entities","count":orphan,"severity":"low" if orphan else "ok"},
      {"type":"temporal","label":"Invalid temporal ranges","count":temporal,"severity":"high" if temporal else "ok"},
      {"type":"unenriched","label":"Awaiting graph enrichment","count":unenriched,"severity":"low" if unenriched else "ok"},
    ]
    return {"score":score,"counts":{"memories":total,"current_memories":current,"historical_memories":total-current,"entities":entities,"relations":relations,"events":events,"conflicts":conflicts,"duplicates":len(duplicates),"low_confidence":low,"stale":stale,"orphaned":orphan,"temporal_errors":temporal,"unenriched":unenriched},"issues":issues,"duplicate_pairs":duplicates,"stale_memories":stale_items}
