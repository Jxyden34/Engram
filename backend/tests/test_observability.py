from time import time
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import observability as obs
from app.database import connect, project_scope


@pytest.fixture
def projects():
    with connect() as conn:
        ids=[str(conn.execute("INSERT INTO projects(slug,name) VALUES (%s,'Metrics test') RETURNING id",
                             ('metrics-'+uuid4().hex,)).fetchone()['id']) for _ in range(2)]
        conn.commit()
    try:
        yield ids
    finally:
        for project in ids:
            with project_scope(project):
                client=obs.redis_client()
                keys=list(client.scan_iter(match=f'engram:observability:v1:{project}:*'))
                if keys:client.delete(*keys)
                with connect() as conn:
                    for table in ['api_keys','document_candidate_memories','document_memory_jobs','documents']:
                        conn.execute('DELETE FROM '+table)
                    conn.commit()
        with connect() as conn:
            conn.execute('DELETE FROM projects WHERE id=ANY(%s::uuid[])',(ids,));conn.commit()


def test_latency_histogram_retention_empty_samples_and_project_isolation(projects):
    moment=time()
    with project_scope(projects[0]),patch.object(obs,'time',return_value=moment):
        obs.observe('api',.010)
        obs.observe('api',.051,True)
        obs.observe('ollama',301)
        result=obs.latency_snapshot()
        api=result['operations']['api']
        assert api['count']==2 and api['errors']==1 and api['error_rate']==.5
        assert api['mean_ms']==30.5 and api['p95_upper_ms']==100
        assert result['operations']['ollama']['p95_overflow']
        assert result['operations']['embedding']['mean_ms'] is None
        key=obs._key('api',int(moment//obs.BUCKET_SECONDS))
        assert 0<obs.redis_client().ttl(key)<=obs.BUCKET_SECONDS*(obs.BUCKET_COUNT+1)
        assert set(obs.redis_client().hgetall(key))=={'count','errors','total_ms','bin:0','bin:2'}
    with project_scope(projects[1]):
        assert obs.latency_snapshot()['operations']['api']['count']==0


def test_telemetry_outage_does_not_change_return_values_or_original_errors():
    @obs.timed('embedding')
    def succeeds(secret):return secret
    @obs.timed('ollama')
    def fails():raise ValueError('Original application error')
    with patch.object(obs,'redis_client',side_effect=ConnectionError('Unavailable')):
        assert succeeds('not recorded')=='not recorded'
        with pytest.raises(ValueError,match='Original application error'):
            fails()
        assert obs.latency_snapshot()['status']=='unavailable'
        assert obs.queue_snapshot()['status']=='unavailable'
    with patch.object(obs,'redis_client') as client:
        obs.observe('arbitrary user-controlled label',1)
        client.assert_not_called()


def test_project_ingestion_and_candidate_denominator_use_rls(projects):
    with project_scope(projects[0]):
        with connect() as conn:
            doc=conn.execute("INSERT INTO documents(filename,object_key,byte_size,sha256,status,uploaded_by,processed_at) VALUES ('private title',%s,10,'test','ready','test',now()) RETURNING id",(uuid4().hex,)).fetchone()['id']
            job=conn.execute("INSERT INTO document_memory_jobs(document_id,requested_by) VALUES (%s,'test') RETURNING id",(doc,)).fetchone()['id']
            for status in ['accepted','rejected','rejected','pending']:
                conn.execute("INSERT INTO document_candidate_memories(job_id,document_id,title,content,status,reviewed_at) VALUES (%s,%s,'Private candidate','Do not expose content',%s,now())",(job,doc,status))
            conn.commit()
        result=obs.project_snapshot()
        assert result['documents']['ready_24h']==1
        assert result['candidates']['acceptance_rate_24h']==pytest.approx(1/3)
        assert result['candidates']['pending']==1
        assert 'private title' not in str(result) and 'Do not expose' not in str(result)
    with project_scope(projects[1]):
        result=obs.project_snapshot()
        assert result['documents']['ready_24h']==0
        assert result['candidates']['acceptance_rate_24h'] is None


def test_metrics_require_admin_session_and_api_timings_are_project_scoped(projects):
    from app.main import app
    from app.security import generate_api_key,hash_password
    name='metrics-admin-'+uuid4().hex
    password=uuid4().hex
    with connect() as conn:
        user=conn.execute('INSERT INTO users(username,password_hash,is_admin) VALUES (%s,%s,true) RETURNING id',(name,hash_password(password))).fetchone()['id'];conn.commit()
    try:
        client=TestClient(app,base_url='http://localhost')
        assert client.get('/api/v1/observability').status_code==401
        token=client.post('/api/v1/mobile/login',json={'username':name,'password':password}).json()['token']
        assert client.get('/api/v1/observability',headers={'Authorization':f'Bearer {token}','X-Engram-Project':projects[0]}).status_code==403
        assert client.post('/api/v1/auth/login',json={'username':name,'password':password}).status_code==200
        headers={'X-Engram-Project':projects[0]}
        with project_scope(projects[0]),connect() as conn:
            key,prefix,digest=generate_api_key()
            conn.execute("INSERT INTO api_keys(name,key_prefix,key_hash,scopes) VALUES ('metrics reader',%s,%s,ARRAY['audit:read'])",(prefix,digest));conn.commit()
        assert client.get('/api/v1/observability',headers={'Authorization':f'Bearer {key}'}).status_code==403
        with patch.object(obs,'_probe',return_value={'status':'ok','latency_ms':1}):
            allowed=client.get('/api/v1/observability',headers=headers)
        assert allowed.status_code==200 and allowed.json()['project_id']==projects[0]
        assert allowed.json()['queue']['status']=='ok'
        assert client.get('/api/v1/memories',headers=headers).status_code==200
        with project_scope(projects[0]):
            assert obs.latency_snapshot()['operations']['api']['count']==1
        with project_scope(projects[1]):
            assert obs.latency_snapshot()['operations']['api']['count']==0
    finally:
        with connect() as conn:
            conn.execute('DELETE FROM sessions WHERE user_id=%s',(user,))
            conn.execute('DELETE FROM users WHERE id=%s',(user,))
            conn.execute('DELETE FROM audit_log WHERE actor=%s',('user:'+name,));conn.commit()
