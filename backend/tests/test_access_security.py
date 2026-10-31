"""Permission and deleted-data regressions using disposable project records."""
import json
from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from app.database import connect, project_scope
from app.security import Principal, client_ip
from app import memories, main


@pytest.fixture
def records():
    name='access-'+uuid4().hex
    with connect() as conn:
        project=str(conn.execute("INSERT INTO projects(slug,name) VALUES (%s,'Access security') RETURNING id",(name,)).fetchone()['id'])
        conn.commit()
    with project_scope(project),connect() as conn:
        memory=str(conn.execute("INSERT INTO memories(title,content,created_by,updated_by) VALUES ('Deleted title','Deleted private content','test','test') RETURNING id").fetchone()['id'])
        conn.execute("INSERT INTO memory_versions(memory_id,version_no,snapshot,actor) VALUES (%s,1,%s::jsonb,'test')",(memory,json.dumps({'content':'Deleted private content'})))
        other=str(conn.execute("INSERT INTO memories(title,content,supersedes_memory_id,created_by,updated_by) VALUES ('Visible title','Visible content',%s,'test','test') RETURNING id",(memory,)).fetchone()['id'])
        conn.execute("INSERT INTO memory_relations(from_memory_id,to_memory_id,relation_type,created_by) VALUES (%s,%s,'supports','test')",(memory,other))
        document=str(conn.execute("INSERT INTO documents(filename,object_key,byte_size,sha256,uploaded_by,status) VALUES ('private.txt',%s,1,'test','test','ready') RETURNING id",(name,)).fetchone()['id'])
        job=str(conn.execute("INSERT INTO document_memory_jobs(document_id,requested_by) VALUES (%s,'test') RETURNING id",(document,)).fetchone()['id'])
        candidate=str(conn.execute("INSERT INTO document_candidate_memories(job_id,document_id,title,content,source_excerpt,nearest_memory_id,comparison) VALUES (%s,%s,'Candidate','Extracted fact','Unapproved private source',%s,'related') RETURNING id",(job,document,memory)).fetchone()['id'])
        chat_job=str(conn.execute("INSERT INTO chat_import_jobs(source_document_id,requested_by) VALUES (%s,'test') RETURNING id",(document,)).fetchone()['id'])
        conversation=str(conn.execute("INSERT INTO chat_import_conversations(import_job_id,title,source_hash) VALUES (%s,'Private chat','test') RETURNING id",(chat_job,)).fetchone()['id'])
        chat_candidate=str(conn.execute("INSERT INTO candidate_memories(import_job_id,import_conversation_id,title,content,source_excerpt,nearest_memory_id,comparison) VALUES (%s,%s,'Chat candidate','Extracted chat fact','Unapproved chat source',%s,'related') RETURNING id",(chat_job,conversation,memory)).fetchone()['id'])
        conn.commit()
    try:
        yield dict(project=project,memory=memory,other=other,candidate=candidate,chat_candidate=chat_candidate)
    finally:
        with project_scope(project),connect() as conn:
            for table in ['candidate_memories','chat_import_conversations','chat_import_jobs','document_candidate_memories','document_memory_jobs','documents','memory_relations','memory_versions','memories']:
                conn.execute('DELETE FROM '+table)
            conn.commit()
        with connect() as conn:
            conn.execute('DELETE FROM projects WHERE id=%s',(project,));conn.commit()


@pytest.fixture
def client(records,monkeypatch):
    principal=Principal('test',None,None,False,{'memory:read','memory:write'},'api_key',records['project'])
    monkeypatch.setattr('app.security.authenticate',lambda request:principal)
    monkeypatch.setattr(main,'authenticate',lambda request:principal)
    monkeypatch.setattr(main,'check_rate',lambda *args:None)
    monkeypatch.setattr(main.observability,'observe',lambda *args:None)
    return TestClient(main.app,base_url='http://localhost',headers={'Authorization':'Bearer test'}),principal


def test_import_source_scope_covers_lists_jobs_updates_and_review(records,client):
    http,p=client
    for family,key in [('documents','candidate'),('chatgpt','chat_candidate')]:
        prefix='/api/v1/imports/'+family
        for method,url,body in [('GET',prefix+'/candidates',None),('GET',prefix+'/jobs',None),('PATCH',prefix+'/candidates/'+records[key],{'title':'Changed'}),('POST',prefix+'/candidates/'+records[key]+'/accept',None),('POST',prefix+'/candidates/'+records[key]+'/reject',None)]:
            assert http.request(method,url,json=body).status_code==403,(method,url)
    p.scopes.add('document:read')
    for family in ['documents','chatgpt']:
        response=http.get('/api/v1/imports/'+family+'/candidates')
        assert response.status_code==200 and response.json()[0]['source_excerpt']
    p.scopes.remove('memory:read')
    assert http.get('/api/v1/imports/documents/candidates').status_code==403


def test_deleted_history_neighbours_and_nearest_content_obey_visibility(records,client):
    http,p=client
    url='/api/v1/memories/'+records['memory']
    assert http.get(url+'/versions').status_code==200
    with project_scope(records['project']),connect() as conn:
        conn.execute('UPDATE memories SET deleted_at=now() WHERE id=%s',(records['memory'],));conn.commit()
    assert http.get(url).status_code==404
    assert http.get(url+'/versions').status_code==404
    p.scopes.add('document:read')
    for family in ['documents','chatgpt']:
        rows=http.get('/api/v1/imports/'+family+'/candidates').json()
        assert len(rows)==1 and rows[0]['nearest_memory_content'] is None
    other=http.get('/api/v1/memories/'+records['other']).json()
    assert other['supersedes'] is None
    assert http.get('/api/v1/memories/'+records['other']+'/relations').json()==[]
    p.is_admin=True
    assert http.get(url+'/versions').json()[0]['snapshot']['content']=='Deleted private content'
    p.project_id='00000000-0000-0000-0000-000000000001'
    assert http.get(url+'/versions').status_code==404


def test_ip_identity_ignores_raw_forwarding_fields():
    request=Request({'type':'http','client':('198.51.100.40',1234),'headers':[(b'cf-connecting-ip',b'203.0.113.2'),(b'x-forwarded-for',b'203.0.113.3')]})
    assert client_ip(request)=='198.51.100.40'


def test_cors_preflight_and_rate_rejection_keep_protocol_semantics(monkeypatch):
    http=TestClient(main.app,base_url='http://localhost',raise_server_exceptions=False)
    for origin,expected in [(main.cfg.public_origin,200),('chrome-extension://'+'a'*32,200),('https://attacker.invalid',400)]:
        result=http.options('/api/v1/memories',headers={'Origin':origin,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'Authorization, X-Engram-Project'})
        assert result.status_code==expected
        assert result.headers.get('access-control-allow-origin')==(origin if expected==200 else None)
    assert http.options('/api/v1/memories').status_code==401
    assert http.get('/api/v1/memories').status_code==401
    def reject(*args):raise HTTPException(429,'Too many requests',headers={'Retry-After':'30'})
    monkeypatch.setattr(main,'check_rate',reject)
    result=http.post('/api/v1/auth/login',json={'username':'nobody','password':'unused'})
    assert result.status_code==429 and result.headers['retry-after']=='30'
