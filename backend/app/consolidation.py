"""Reviewed cluster drafts reuse project-scoped evidence snapshots and source fingerprints."""

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from app import memories,reflection
from app.database import connect
from app.schemas import BriefCreate,ClusterApproveRequest


def create_draft(memory_ids,actor):
    ids = [str(key) for key in memory_ids]
    if len(set(ids)) != len(ids) or not 3 <= len(ids) <= 10:
        raise HTTPException(status_code=422,detail='Choose 3–10 distinct current memories')
    result = reflection.reflect('Propose a concise cluster summary from these selected facts. Preserve every important distinction, date and uncertainty.',
                                'deep',source_ids=ids)
    cited = {citation['source'] for claim in result['claims'] for citation in claim['citations']}
    if result['insufficient'] or any(gap['kind']=='conflicting' for gap in result.get('gaps',[])) or cited != set(range(1,len(result['sources'])+1)):
        raise HTTPException(status_code=502,detail='The draft did not cite every source. Try a smaller, more closely related group.')
    body = BriefCreate(title='Cluster consolidation draft',question=result['question'],budget='deep',
                       project_revision=result['project_revision'],claims=result['claims'],
                       sources=[{'id':source['id'],'version':source['version']} for source in result['sources']])
    saved = reflection.save_brief(body,actor,purpose='consolidation')
    return get_draft(str(saved['id']))


def list_drafts():
    with connect() as conn:
        return [dict(row) for row in conn.execute("""SELECT id,title,created_at,snapshot->>'result_memory_id' AS result_memory_id
            FROM project_briefs WHERE snapshot->>'purpose'='consolidation' ORDER BY created_at DESC LIMIT 100""").fetchall()]


def get_draft(draft_id):
    with connect() as conn:
        row = conn.execute("SELECT snapshot FROM project_briefs WHERE id=%s AND snapshot->>'purpose'='consolidation'",(draft_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404,detail='Cluster draft not found')
    result = reflection.get_brief(draft_id)
    result['source_versions'] = {ref['id']:ref['version'] for ref in row['snapshot']['sources']}
    result['result_memory_id'] = row['snapshot'].get('result_memory_id')
    result['content'] = '\n\n'.join(claim['text'] for claim in result['claims'])
    return result


def approve(draft_id:str,body:ClusterApproveRequest,actor:str):
    if not body.title.strip() or not body.content.strip():
        raise HTTPException(status_code=422,detail='Review the title and summary before saving')
    with connect() as conn:
        row = conn.execute("SELECT snapshot FROM project_briefs WHERE id=%s AND snapshot->>'purpose'='consolidation' FOR UPDATE",(draft_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404,detail='Cluster draft not found')
        snapshot = row['snapshot']
        if snapshot.get('result_memory_id'):
            return {'status':'accepted','result_memory_id':snapshot['result_memory_id']}
        expected = {ref['id']:ref['version'] for ref in snapshot['sources']}
        if {str(key):value for key,value in body.source_versions.items()} != expected:
            raise HTTPException(status_code=409,detail='Reload this draft before approving')
        sources = reflection._load_sources(conn,snapshot['sources'],lock=True)
        if len(sources) != len(expected) or any(not reflection._current(source) or reflection._version(source) != expected[str(source['id'])] for source in sources.values()):
            raise HTTPException(status_code=409,detail='Source evidence changed. Generate a fresh draft.')
        vector = memories.embed_literal(body.title+'\n'+body.content)
        created = conn.execute('''INSERT INTO memories(title,content,source_type,source_ref,metadata,created_by,updated_by,embedding,confidence,source_trust)
            VALUES (%s,%s,'cluster_review',%s,%s,%s,%s,%s::vector,%s,%s) RETURNING id''',
            (body.title.strip(),body.content.strip(),draft_id,Jsonb({'source_memory_ids':list(expected),
             'source_versions':expected,'reviewed_claims':snapshot['claims']}),actor,actor,vector,
             min(source['confidence'] for source in sources.values()),min(source['source_trust'] for source in sources.values()))).fetchone()
        for source_id in expected:
            conn.execute("INSERT INTO memory_relations(from_memory_id,to_memory_id,relation_type,created_by) VALUES (%s,%s,'derived_from',%s)",
                         (created['id'],source_id,actor))
        conn.execute("UPDATE project_briefs SET snapshot=snapshot || %s WHERE id=%s",
                     (Jsonb({'result_memory_id':str(created['id']),'reviewed_by':actor}),draft_id))
        memories.record_consolidation(conn,created['id'],actor)
        conn.commit()
    memories._queue_enrichment(str(created['id']),actor)
    return {'status':'accepted','result_memory_id':str(created['id'])}
