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
                    conn.execute('DELETE FROM memories')
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
                       sources=[{'id': s['id'], 'version': s['version']} for s in result['sources']])


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
    saved = client.post(path, headers=headers, json=body)
    assert saved.status_code == 201
    brief_id = saved.json()['id']
    assert client.get(path+'/'+brief_id, headers=read_headers).json()['status'] == 'current'
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
