from uuid import uuid4
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.database import connect,DEFAULT_PROJECT_ID
from app.security import Principal,hash_password


def test_branding_rejects_unsafe_logo_and_unreadable_colours():
    from app.commercial.routes import Branding
    from pydantic import ValidationError
    for payload in [{'logo':'javascript:alert(1)'},{'logo':'data:image/svg+xml;base64,PHN2Zz4='},{'accent':'#000000'},{'name':'  '}]:
        with pytest.raises(ValidationError):Branding(**payload)
    assert Branding(name=' Example ').name=='Example'


def test_handover_exports_user_content_as_text():
    from app.commercial.handover import markdown
    data={'project':{'name':'Example'},'generated_at':'now','summary':'One memory',
          'limitations':'Bounded export','decisions':[],'outstanding_questions':[], 'briefs':[],
          'sources':[{'id':'id','title':'<script>test</script>','content':'![tracking](https://example.com/pixel)',
                      'updated_at':'now','source_ref':None,'content_truncated':False}]}
    text=markdown(data)
    assert '\n```text\n<script>test</script>\n```' in text
    assert '\n```text\n![tracking]' in text


def test_team_invitation_role_and_project_isolation(monkeypatch,tmp_path):
    from app import edition,licensing
    from app.commercial import routes as business_routes
    from app.commercial import workspaces
    from app.main import app as main_app,security_middleware
    from fastapi import FastAPI
    from app.projects import resolve_project
    monkeypatch.setattr(edition,'get_edition',lambda:'commercial')
    monkeypatch.setattr(business_routes,'get_edition',lambda:'commercial')
    monkeypatch.setattr(licensing,'require_commercial_license',lambda:None)
    # Include Commercial routes before the main application's terminal MCP mount.
    app=FastAPI()
    app.middleware('http')(security_middleware)
    app.include_router(business_routes.router)
    app.mount('/',main_app.router)
    unique=uuid4().hex[:10];username='team-'+unique
    with connect() as conn:
        owner=conn.execute('INSERT INTO users(username,password_hash,is_admin) VALUES(%s,%s,true) RETURNING id',('owner-'+unique,hash_password('team-owner-test-password'))).fetchone()['id']
        project=str(conn.execute('INSERT INTO projects(name,slug) VALUES(%s,%s) RETURNING id',('Team',unique)).fetchone()['id']);conn.commit()
    principal=Principal('test',str(owner),'owner',True,set(),'session')
    from app.database import project_scope
    try:
        with project_scope(project):
            invitation=workspaces.invite(principal,username,'viewer')
        account=workspaces.accept(invitation['token'],'team-member-test-password')
        with pytest.raises(HTTPException) as error:workspaces.accept(invitation['token'],'team-member-test-password')
        assert error.value.status_code==410
        client=TestClient(app)
        token_file=tmp_path/'setup-token';token_file.write_text('a'*48)
        from app.config import settings
        monkeypatch.setattr(settings(),'setup_bootstrap_token_file',str(token_file))
        body={'username':'new-admin','password':'secure-setup-password','token':'b'*48}
        assert client.post('/api/v1/setup/bootstrap',json=body).status_code==403
        assert client.post('/api/v1/setup/bootstrap',json={**body,'token':'a'*48}).status_code==409
        login=client.post('/api/v1/mobile/login',json={'username':username,'password':'team-member-test-password'})
        headers={'Authorization':'Bearer '+login.json()['token'],'X-Engram-Project':project}
        items=client.get('/api/v1/projects',headers=headers).json()
        assert [str(item['id']) for item in items]==[project]
        assert client.get('/api/v1/memories',headers=headers).status_code==200
        assert client.post('/api/v1/memories',headers=headers,json={'title':'No','content':'Viewer cannot edit'}).status_code==403
        assert client.get('/api/v1/memories',headers={**headers,'X-Engram-Project':DEFAULT_PROJECT_ID}).status_code==404
        assert client.post('/api/v1/team/invitations',headers=headers,json={'username':'outsider','role':'owner'}).status_code==403
        assert client.put('/api/v1/setup/models',headers=headers,json={'model':'arbitrary-model'}).status_code==403
        with project_scope(project):
            with connect() as conn:
                memory=str(conn.execute("INSERT INTO memories(title,content,memory_type,created_by,updated_by) VALUES('Team decision','Approved evidence','decision','test','test') RETURNING id").fetchone()['id']);conn.commit()
        exported=client.get('/api/v1/handover',headers=headers)
        assert exported.status_code==200
        assert [str(row['id']) for row in exported.json()['sources']]==[memory]
        from datetime import datetime,timedelta,timezone
        reminder={'memory_id':memory,'due_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'note':'Revisit'}
        first=client.post('/api/v1/reminders',headers=headers,json=reminder)
        assert first.status_code==201
        identifier=first.json()['id']
        assert client.post('/api/v1/reminders',headers=headers,json=reminder).json()['id']==identifier
        owner_login=client.post('/api/v1/mobile/login',json={'username':'owner-'+unique,'password':'team-owner-test-password'})
        owner_headers={'Authorization':'Bearer '+owner_login.json()['token'],'X-Engram-Project':project}
        assert client.get('/api/v1/reminders',headers=owner_headers).json()==[]
        assert client.patch('/api/v1/reminders/'+identifier,headers=owner_headers,json={'status':'done'}).status_code==404
        assert len(client.get('/api/v1/reminders',headers=headers).json())==1
        assert client.patch('/api/v1/reminders/'+identifier,headers=headers,json={'status':'done'}).status_code==200
        assert client.get('/api/v1/reminders',headers=headers).json()==[]
        with connect() as conn:
            member=conn.execute('SELECT id FROM users WHERE username=%s',(username,)).fetchone()['id']
        bound=Principal('oauth',str(member),username,False,{'memory:write','memory:read','mcp:use'},'oauth',project)
        assert resolve_project(bound,project)==project
        assert 'memory:write' not in bound.scopes
        with project_scope(project):workspaces.set_member(principal,username,None)
        assert client.get('/api/v1/memories',headers=headers).status_code==404
        with pytest.raises(HTTPException):resolve_project(bound,project)
    finally:
        with project_scope(project):
            with connect() as conn:
                conn.execute('DELETE FROM audit_log WHERE project_id=%s',(project,))
                conn.execute('DELETE FROM memories WHERE project_id=%s',(project,));conn.commit()
        with connect() as conn:
            conn.execute('DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username IN (%s,%s))',(username,'owner-'+unique))
            conn.execute('DELETE FROM projects WHERE id=%s',(project,))
            conn.execute('DELETE FROM users WHERE username IN (%s,%s)',(username,'owner-'+unique));conn.commit()


def test_reminders_require_future_timezone_aware_dates():
    from app.reminders import Reminder
    from pydantic import ValidationError
    for value in ['2020-01-01T12:00:00Z','2030-01-01T12:00:00']:
        with pytest.raises(ValidationError):Reminder(memory_id=uuid4(),due_at=value)
