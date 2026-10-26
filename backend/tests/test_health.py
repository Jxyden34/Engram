from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import connect, project_scope
from app.security import hash_password


def test_memory_quality_endpoint_runs_real_summary_and_keeps_project_scope():
    from app.main import app

    name='health-'+uuid4().hex
    password=uuid4().hex
    with connect() as conn:
        user=conn.execute('INSERT INTO users(username,password_hash,is_admin) VALUES (%s,%s,true) RETURNING id',
                          (name,hash_password(password))).fetchone()['id']
        projects=[str(conn.execute("INSERT INTO projects(slug,name,created_by) VALUES (%s,'Health test',%s) RETURNING id",
                                   (name+'-'+str(index),user)).fetchone()['id']) for index in range(2)]
        conn.commit()
    try:
        with project_scope(projects[0]),connect() as conn:
            conn.execute("INSERT INTO memories(title,content,created_by,updated_by) VALUES ('Quality test','Private project fact','test','test')")
            conn.commit()
        client=TestClient(app,base_url='http://localhost')
        assert client.get('/health').status_code==200
        assert client.get('/health').json()['service']=='engram'
        assert client.get('/api/v1/health/summary').status_code==401
        assert client.post('/api/v1/auth/login',json={'username':name,'password':password}).status_code==200
        populated=client.get('/api/v1/health/summary',headers={'X-Engram-Project':projects[0]})
        assert populated.status_code==200
        data=populated.json()
        assert 0<=data['score']<=100
        assert data['counts']['current_memories']==1
        assert data['issues'] and data['duplicate_pairs']==[] and data['stale_memories']==[]
        empty=client.get('/api/v1/health/summary',headers={'X-Engram-Project':projects[1]})
        assert empty.status_code==200 and empty.json()['counts']['current_memories']==0
    finally:
        for project in projects:
            with project_scope(project),connect() as conn:
                conn.execute('DELETE FROM memories');conn.commit()
        with connect() as conn:
            conn.execute('DELETE FROM sessions WHERE user_id=%s',(user,))
            conn.execute('DELETE FROM projects WHERE id=ANY(%s::uuid[])',(projects,))
            conn.execute('DELETE FROM users WHERE id=%s',(user,))
            conn.execute('DELETE FROM audit_log WHERE actor=%s',('user:'+name,))
            conn.commit()
