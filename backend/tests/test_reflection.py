from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import reflection
from app.database import connect, project_scope
from app.schemas import BriefCreate

CONTENT = 'The project uses local Ollama and keeps PostgreSQL as the source of truth.'
MODEL = {'claims': [{'text': 'The project uses local AI.',
                    'citations': [{'source': 1, 'quote': 'The project uses local Ollama'}]}], 'insufficient': False}


@pytest.fixture
def corpus():
    with connect() as conn:
        projects = [str(conn.execute("INSERT INTO projects(slug,name) VALUES (%s,'Reflection test') RETURNING id",
                    ('reflect-'+uuid4().hex,)).fetchone()['id']) for _ in range(2)]
        conn.commit()
    with project_scope(projects[0]):
        with connect() as conn:
            source = dict(conn.execute('''INSERT INTO memories(title,content,created_by,updated_by)
                VALUES ('Project architecture',%s,'test','test') RETURNING *''', (CONTENT,)).fetchone())
            conn.commit()
    try:
        yield projects, source
    finally:
        for project in projects:
            with project_scope(project):
                with connect() as conn:
                    conn.execute('DELETE FROM project_briefs')
                    conn.execute('DELETE FROM audit_log')
                    conn.execute('DELETE FROM api_keys')
                    conn.execute('DELETE FROM memory_versions')
                    conn.execute('DELETE FROM memory_relations')
                    conn.execute('DELETE FROM memories')
                    conn.execute('DELETE FROM document_chunks')
                    conn.execute('DELETE FROM documents')
                    conn.commit()
        with connect() as conn:
            conn.execute('DELETE FROM projects WHERE id=ANY(%s::uuid[])', (projects,))
            conn.commit()


def draft(source, budget='standard'):
    with patch.object(reflection.intelligence, 'search_memories', return_value=[source]), \
            patch.object(reflection, '_ollama_json', return_value=MODEL):
        return reflection.reflect('What guides this project?', budget)


def save_body(result):
    return BriefCreate(title='Architecture brief', question=result['question'], budget=result['budget'],
                       project_revision=result['project_revision'], claims=result['claims'],
                       include_documents=bool(result.get('include_documents')),
                       reasoning=bool(result.get('reasoning')),
                       as_of=result.get('as_of'),
                       sources=[{'id': s['id'], 'version': s['version'],'kind':s.get('kind','memory')} for s in result['sources']])


@pytest.mark.parametrize('budget,limit,chars', [('quick', 6, 4000), ('standard', 12, 9000), ('deep', 20, 16000)])
def test_reflection_bounds_evidence_and_uses_current_only_sources(corpus, budget, limit, chars):
    projects, source = corpus
    rows = [{**source, 'id': uuid4(), 'content': CONTENT+'x'*2000} for _ in range(limit)]
    with project_scope(projects[0]), patch.object(reflection.intelligence, 'search_memories', return_value=rows) as search, \
            patch.object(reflection, '_ollama_json', return_value=MODEL):
        result = reflection.reflect('What guides this project?', budget)
    search.assert_called_once_with('What guides this project?', limit, infer_history=False)
    assert sum(len(s['content']) for s in result['sources']) <= chars
    assert result['claims'] == MODEL['claims']


@pytest.mark.parametrize('answer', [
    {'claims': [{'text': 'Unsupported', 'citations': [{'source': 20, 'quote': CONTENT}]}], 'insufficient': False},
    {'claims': [{'text': 'Unsupported', 'citations': [{'source': True, 'quote': CONTENT}]}], 'insufficient': False},
    {'claims': [{'text': 'Unsupported', 'citations': [{'source': 1, 'quote': 'The project uses the cloud'}]}], 'insufficient': False},
    {'claims': [], 'insufficient': False},
    {'claims': [], 'insufficient': 'false'},
])
def test_reflection_rejects_invalid_generated_evidence(corpus, answer):
    projects, source = corpus
    with project_scope(projects[0]), patch.object(reflection.intelligence, 'search_memories', return_value=[source]), \
            patch.object(reflection, '_ollama_json', return_value=answer):
        with pytest.raises(HTTPException) as error:
            reflection.reflect('What guides this project?', 'standard')
        assert error.value.status_code == 502


def test_empty_evidence_abstains_without_model_call(corpus):
    projects, _ = corpus
    with project_scope(projects[0]), patch.object(reflection.intelligence, 'search_memories', return_value=[]), \
            patch.object(reflection, '_ollama_json') as model:
        assert reflection.reflect('Unknown fact?', 'quick')['insufficient'] is True
    model.assert_not_called()


def test_brief_lifecycle_isolation_new_evidence_and_stale_save(corpus):
    projects, source = corpus
    with project_scope(projects[0]):
        result = draft(source)
        body = save_body(result)
        saved = reflection.save_brief(body, 'test')
        brief_id = str(saved['id'])
        assert reflection.get_brief(brief_id)['status'] == 'current'
        assert reflection.list_briefs()[0]['title'] == body.title
        with connect() as conn:
            assert conn.execute('SELECT content FROM memories WHERE id=%s', (source['id'],)).fetchone()['content'] == CONTENT
            conn.execute("INSERT INTO memories(title,content,created_by,updated_by) VALUES ('New fact','New evidence','test','test')")
            conn.commit()
        brief = reflection.get_brief(brief_id)
        assert brief['status'] == 'needs_review' and brief['claims'] == MODEL['claims']
        assert brief['evidence_changed'] is False
        with pytest.raises(HTTPException) as stale:
            reflection.save_brief(body, 'test')
        assert stale.value.status_code == 409
        with connect() as conn:
            conn.execute("UPDATE memories SET content='The architecture has changed',updated_at=now() WHERE id=%s", (source['id'],))
            conn.commit()
        brief = reflection.get_brief(brief_id)
        assert brief['status'] == 'needs_review' and brief['claims'] == []
        assert brief['sources'][0]['status'] == 'changed'
        with connect() as conn:
            conn.execute('UPDATE memories SET deleted_at=now() WHERE id=%s', (source['id'],))
            conn.commit()
        assert reflection.get_brief(brief_id)['sources'][0]['status'] == 'unavailable'
    with project_scope(projects[1]):
        assert reflection.list_briefs() == []
        for action in (reflection.get_brief, reflection.delete_brief):
            with pytest.raises(HTTPException) as missing:
                action(brief_id)
            assert missing.value.status_code == 404
        # Even a deliberately forged revision cannot import another project's evidence.
        with connect() as conn:
            foreign_revision = reflection._revision(conn)
        with pytest.raises(HTTPException) as missing_source:
            reflection.save_brief(body.model_copy(update={'project_revision': foreign_revision}), 'test')
        assert missing_source.value.status_code == 409
    with project_scope(projects[0]):
        assert reflection.delete_brief(brief_id)['status'] == 'deleted'
        assert reflection.list_briefs() == []


def test_reflection_detects_memories_changed_during_generation(corpus):
    projects, source = corpus
    def changed(*_args, **_kwargs):
        with connect() as conn:
            conn.execute('UPDATE memories SET updated_at=now() WHERE id=%s', (source['id'],))
            conn.commit()
        return MODEL
    with project_scope(projects[0]), patch.object(reflection.intelligence, 'search_memories', return_value=[source]), \
            patch.object(reflection, '_ollama_json', side_effect=changed):
        with pytest.raises(HTTPException) as error:
            reflection.reflect('What guides this project?', 'standard')
        assert error.value.status_code == 409


def test_brief_api_enforces_scopes_and_bound_projects(corpus):
    from app.main import app
    from app.security import generate_api_key
    projects, source = corpus
    with project_scope(projects[0]):
        body = save_body(draft(source)).model_dump(mode='json')
        writer, reader = None, None
        with connect() as conn:
            for name, scopes in [('writer', ['memory:read', 'memory:write']), ('reader', ['memory:read'])]:
                token, prefix, digest = generate_api_key()
                conn.execute('INSERT INTO api_keys(name,key_prefix,key_hash,scopes) VALUES (%s,%s,%s,%s)',
                             (name, prefix, digest, scopes))
                if name == 'writer':
                    writer = token
                else:
                    reader = token
            conn.commit()
    client = TestClient(app, base_url='http://localhost')
    headers = {'Authorization': f'Bearer {writer}'}
    read_headers = {'Authorization': f'Bearer {reader}'}
    path = '/api/v1/intelligence/briefs'
    assert client.post(path, headers=read_headers, json=body).status_code == 403
    assert client.post('/api/v1/intelligence/reflect',headers=read_headers,
                       json={'question':'Documents?','include_documents':True}).status_code == 403
    saved = client.post(path, headers=headers, json=body)
    assert saved.status_code == 201
    brief_id = saved.json()['id']
    assert client.get(path+'/'+brief_id, headers=read_headers).json()['status'] == 'current'
    with patch.object(reflection.intelligence,'search_memories',return_value=[source]), \
            patch.object(reflection,'_ollama_json',return_value=MODEL):
        refreshed = client.post(path+'/'+brief_id+'/refresh',headers=read_headers)
    assert refreshed.status_code == 200 and refreshed.json()['refresh_of'] == brief_id
    assert client.get(path, headers={**headers, 'X-Engram-Project': projects[1]}).status_code == 403
    assert client.delete(path+'/'+brief_id, headers=read_headers).status_code == 403
    assert client.delete(path+'/'+brief_id, headers=headers).status_code == 200
    archive_path = f"/api/v1/memories/{source['id']}/archive"
    archive_body = {'archived':True,'expected_updated_at':source['updated_at'].isoformat(),'reason':'Archive API check'}
    assert client.post(archive_path,headers=read_headers,json=archive_body).status_code == 403
    assert client.post(archive_path,headers=headers,json=archive_body).status_code == 200


def test_archival_is_searchable_reversible_and_invalidates_briefs(corpus):
    from app import memories, intelligence
    projects, source = corpus
    vector = '['+','.join(['1']+['0']*383)+']'
    with project_scope(projects[0]), patch.object(intelligence,'embed_literal',return_value=vector):
        saved = reflection.save_brief(save_body(draft(source)), 'reviewer')
        archived = memories.set_archived(str(source['id']),True,source['updated_at'],'test','Cold project evidence')
        assert archived['content'] == CONTENT and archived['archived_at'] is not None
        assert memories.list_memories() == []
        assert intelligence.search_memories('project',10) == []
        assert [str(row['id']) for row in intelligence.search_memories('project',10,include_archived=True)] == [str(source['id'])]
        assert memories.list_memories(include_archived=True)[0]['archived_at']
        assert memories.get(str(source['id']),touch=False)['content'] == CONTENT
        brief = reflection.get_brief(str(saved['id']))
        assert brief['claims'] == [] and brief['sources'][0]['status'] == 'unavailable'
        with patch.object(reflection,'_ollama_json') as model:
            assert reflection.reflect('project','quick')['insufficient'] is True
        model.assert_not_called()
        with pytest.raises(HTTPException) as stale:
            memories.set_archived(str(source['id']),False,source['updated_at'],'test','Stale restore')
        assert stale.value.status_code == 409
        restored = memories.set_archived(str(source['id']),False,archived['updated_at'],'test','Restore relevant evidence')
        assert restored['archived_at'] is None and restored['content'] == CONTENT
        assert len(memories.versions(str(source['id']))) == 2
        assert len(memories.list_memories()) == 1
        assert reflection.get_brief(str(saved['id']))['status'] == 'needs_review'
    with project_scope(projects[1]):
        with pytest.raises(HTTPException) as missing:
            memories.set_archived(str(source['id']),True,restored['updated_at'],'test','Wrong project')
        assert missing.value.status_code == 404


def test_brief_refresh_uses_current_evidence_and_preserves_previous_snapshot(corpus):
    projects, source = corpus
    with project_scope(projects[0]):
        previous = reflection.save_brief(save_body(draft(source)), 'reviewer')
        previous_id = str(previous['id'])
        with connect() as conn:
            original_snapshot = conn.execute('SELECT snapshot FROM project_briefs WHERE id=%s',(previous_id,)).fetchone()['snapshot']
            updated = dict(conn.execute('UPDATE memories SET content=%s,updated_at=now() WHERE id=%s RETURNING *',
                            (CONTENT+' A new reviewed decision.',source['id'])).fetchone())
            conn.commit()
        with patch.object(reflection.intelligence,'search_memories',return_value=[updated]), \
                patch.object(reflection,'_ollama_json',return_value=MODEL) as model:
            preview = reflection.refresh_brief(previous_id)
        assert preview['refresh_of'] == previous_id and preview['refresh_title'] == previous['title']
        assert MODEL['claims'][0]['text'] not in model.call_args.args[1], 'Stale generated text must not become new evidence'
        with connect() as conn:
            assert conn.execute('SELECT count(*) AS n FROM project_briefs').fetchone()['n'] == 1, 'Refresh is a preview, never an automatic save'
        body = save_body(preview).model_copy(update={'refresh_of': previous['id']})
        fresh = reflection.save_brief(body,'reviewer')
        assert str(fresh['id']) != previous_id
        assert reflection.get_brief(str(fresh['id']))['status'] == 'current'
        assert reflection.get_brief(str(fresh['id']))['refresh_of'] == previous_id
        changes = reflection.get_brief(str(fresh['id']))['changes']
        assert changes['unchanged'] == 1 and changes['added'] == changes['removed'] == []
        assert changes['sources'][0]['state'] == 'changed'
        with connect() as conn:
            assert conn.execute('SELECT snapshot FROM project_briefs WHERE id=%s',(previous_id,)).fetchone()['snapshot'] == original_snapshot
        with pytest.raises(HTTPException) as changed_question:
            reflection.save_brief(body.model_copy(update={'question':'A different question?'}),'reviewer')
        assert changed_question.value.status_code == 422
    with project_scope(projects[1]), patch.object(reflection,'_ollama_json') as model:
        with pytest.raises(HTTPException) as missing:
            reflection.refresh_brief(previous_id)
        assert missing.value.status_code == 404
        with pytest.raises(HTTPException) as wrong_parent:
            reflection.save_brief(body,'reviewer')
        assert wrong_parent.value.status_code == 404
    model.assert_not_called()


def test_document_reflection_checks_provenance_scopes_changes_and_rls(corpus):
    from app import documents
    projects, _ = corpus
    text = 'The backup window starts at midnight and lasts one hour.'
    model = {'claims':[{'text':'The backup starts at midnight.',
              'citations':[{'source':1,'quote':'backup window starts at midnight'}]}],'insufficient':False}
    with project_scope(projects[0]):
        with connect() as conn:
            document = conn.execute('''INSERT INTO documents(filename,object_key,byte_size,sha256,status,uploaded_by)
                VALUES ('Backup plan',%s,100,'qa','ready','test') RETURNING id''',(uuid4().hex,)).fetchone()['id']
            chunk = conn.execute('INSERT INTO document_chunks(document_id,chunk_index,content) VALUES (%s,0,%s) RETURNING id',
                                (document,text)).fetchone()['id']
            conn.commit()
        with patch.object(reflection.intelligence,'search_memories',return_value=[]), \
                patch.object(documents,'search_chunks',return_value=[{'id':chunk,'semantic_score':1}]), \
                patch.object(reflection,'_ollama_json',return_value=model):
            result = reflection.reflect('When does backup start?','quick',include_documents=True)
        assert result['sources'][0]['kind'] == 'document_chunk'
        assert result['sources'][0]['document_id'] == str(document)
        saved = reflection.save_brief(save_body(result),'test')
        brief_id = str(saved['id'])
        assert reflection.list_briefs() == []
        assert reflection.list_briefs(allow_documents=True)[0]['id'] == saved['id']
        for action in (reflection.get_brief,reflection.refresh_brief):
            with pytest.raises(HTTPException) as forbidden:
                action(brief_id)
            assert forbidden.value.status_code == 403
        assert reflection.get_brief(brief_id,allow_documents=True)['status'] == 'current'
        with connect() as conn:
            conn.execute('UPDATE document_chunks SET content=%s WHERE id=%s',(text+' Revised.',chunk));conn.commit()
        assert reflection.get_brief(brief_id,allow_documents=True)['claims'] == []
        with pytest.raises(HTTPException) as stale:
            reflection.save_brief(save_body(result),'test')
        assert stale.value.status_code == 409
    with project_scope(projects[1]), patch.object(reflection.intelligence,'search_memories',return_value=[]), \
            patch.object(documents,'search_chunks',return_value=[{'id':chunk,'semantic_score':1}]), \
            patch.object(reflection,'_ollama_json') as llm:
        assert reflection.reflect('Backup?','quick',include_documents=True)['sources'] == []
    llm.assert_not_called()


def test_brief_comparison_tracks_text_changes_and_redacts_unavailable_evidence(corpus):
    projects,source = corpus
    with project_scope(projects[0]):
        original = draft(source)
        previous = reflection.save_brief(save_body(original),'test')
        new_claim = {**original['claims'][0],'text':'A newly reviewed local AI conclusion.'}
        body = save_body({**original,'claims':[new_claim]}).model_copy(update={'refresh_of':previous['id']})
        saved = reflection.save_brief(body,'test')
        changes = reflection.get_brief(str(saved['id']))['changes']
        assert changes['added'] == [new_claim['text']]
        assert changes['removed'] == [original['claims'][0]['text']]
        with connect() as conn:
            conn.execute('UPDATE memories SET deleted_at=now() WHERE id=%s',(source['id'],));conn.commit()
        changes = reflection.get_brief(str(saved['id']))['changes']
        assert changes['added'] == changes['removed'] == [] and changes['redacted'] == 2
        reflection.delete_brief(str(previous['id']))
        assert reflection.get_brief(str(saved['id']))['changes'] == {'available':False}


@pytest.mark.parametrize('invalid_plan',[False,True])
def test_followup_searches_are_bounded_deduplicated_and_transparent(corpus,invalid_plan):
    projects,source = corpus
    plan = {'queries':['Architecture details','Review rules']} if not invalid_plan else {'queries':['x'*301]}
    with project_scope(projects[0]), patch.object(reflection.intelligence,'search_memories',return_value=[source]) as search, \
            patch.object(reflection,'_ollama_json',side_effect=[plan,MODEL]):
        result = reflection.reflect('What guides this project?','deep',reasoning=True)
    assert len(result['sources']) == 1, 'Duplicate sources from several searches must share one citation number'
    assert search.call_count == (1 if invalid_plan else 3)
    assert result['reasoning_status'] == ('followup_unavailable' if invalid_plan else 'expanded')
    assert len(result['search_queries']) == search.call_count
    assert result['evidence_chars'] <= 16000


def test_cluster_review_preserves_sources_provenance_and_retry_state(corpus):
    from app import consolidation,memories
    from app.schemas import ClusterApproveRequest
    projects,source=corpus
    ids=[source['id']]
    texts=[CONTENT,'The service keeps original records traceable.','Every generated summary requires human approval.']
    with project_scope(projects[0]):
        with connect() as conn:
            for text in texts[1:]:
                ids.append(conn.execute("INSERT INTO memories(title,content,confidence,source_trust,created_by,updated_by) VALUES ('Cluster source',%s,.4,.7,'test','test') RETURNING id",(text,)).fetchone()['id'])
            conn.commit()
        generated={'claims':[{'text':text,'citations':[{'source':i+1,'quote':text}]} for i,text in enumerate(texts)],'insufficient':False}
        with patch.object(reflection,'_ollama_json',return_value=generated):
            drafted=consolidation.create_draft(ids,'test')
        assert reflection.list_briefs()==[] and len(consolidation.list_drafts())==1
        body=ClusterApproveRequest(title='Reviewed summary',content=drafted['content'],source_versions=drafted['source_versions'])
        with patch.object(memories,'embed_literal',return_value='['+','.join(['1']+['0']*383)+']'),patch.object(memories,'_queue_enrichment'):
            saved=consolidation.approve(drafted['id'],body,'reviewer')
            assert consolidation.approve(drafted['id'],body,'reviewer')==saved
        summary=memories.get(saved['result_memory_id'],touch=False)
        assert float(summary['confidence'])==.4 and len(memories.relations(saved['result_memory_id']))==3
        assert [memories.get(str(key),touch=False)['content'] for key in ids]==texts
        with patch.object(reflection,'_ollama_json',return_value=generated):
            stale=consolidation.create_draft(ids,'test')
        with connect() as conn:
            conn.execute('UPDATE memories SET updated_at=now() WHERE id=%s',(ids[0],));conn.commit()
        with pytest.raises(HTTPException) as changed:
            consolidation.approve(stale['id'],body,'reviewer')
        assert changed.value.status_code==409
    with project_scope(projects[1]):
        for action in (lambda:consolidation.get_draft(drafted['id']),lambda:consolidation.create_draft(ids,'test')):
            with pytest.raises(HTTPException) as missing:
                action()
            assert missing.value.status_code==404


def test_point_in_time_uses_recorded_version_not_current_or_future_facts(corpus):
    from datetime import datetime,timezone
    from psycopg.types.json import Jsonb
    projects,source=corpus
    point=datetime(2022,1,1,tzinfo=timezone.utc)
    with project_scope(projects[0]):
        with connect() as conn:
            current=dict(conn.execute("UPDATE memories SET title='Atlas',content='Atlas server runs on beta today.',created_at='2019-01-01',updated_at='2025-01-01',valid_from='2019-01-01' WHERE id=%s RETURNING *",(source['id'],)).fetchone())
            old={key:value for key,value in current.items() if key!='embedding'}
            old.update(content='Atlas server runs on alpha.',updated_at='2020-01-01T00:00:00+00:00')
            conn.execute("INSERT INTO memory_versions(memory_id,version_no,snapshot,actor,created_at) VALUES (%s,1,%s,'test','2024-01-01')",
                         (source['id'],Jsonb(old,dumps=lambda value:__import__('json').dumps(value,default=str))))
            conn.execute("INSERT INTO memories(title,content,created_by,updated_by,created_at,updated_at,valid_from) VALUES ('Atlas future','Atlas future knowledge','test','test','2023-01-01','2023-01-01','2023-01-01')")
            conn.commit()
        model={'claims':[{'text':'Atlas used alpha.','citations':[{'source':1,'quote':'server runs on alpha'}]}],'insufficient':False}
        with patch.object(reflection,'_ollama_json',return_value=model),patch.object(reflection.intelligence,'search_memories') as present_search:
            result=reflection.reflect('Atlas server','quick',as_of=point)
        present_search.assert_not_called()
        assert len(result['sources'])==1 and result['sources'][0]['content']=='Atlas server runs on alpha.'
        saved=reflection.save_brief(save_body(result),'test')
        assert reflection.get_brief(str(saved['id']))['as_of']==point.isoformat()
        with connect() as conn:
            conn.execute('UPDATE memories SET deleted_at=now() WHERE id=%s',(source['id'],));conn.commit()
        assert reflection.get_brief(str(saved['id']))['claims']==[]
    with project_scope(projects[1]),patch.object(reflection,'_ollama_json') as llm:
        assert reflection.reflect('Atlas server','quick',as_of=point)['sources']==[]
    llm.assert_not_called()


@pytest.mark.parametrize('options',[{'as_of':'2022-01-01T00:00:00'},{'as_of':'2022-01-01T00:00:00Z','include_documents':True}])
def test_point_in_time_rejects_ambiguous_or_unversioned_evidence(options):
    from pydantic import ValidationError
    from app.schemas import ReflectRequest
    with pytest.raises(ValidationError):
        ReflectRequest(question='Past facts?',**options)
