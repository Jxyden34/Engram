from uuid import uuid4
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.database import connect,DEFAULT_PROJECT_ID
from app.security import Principal,hash_password


def test_branding_rejects_unsafe_logo_and_unreadable_colours():
    from app.business_routes import Branding
    from pydantic import ValidationError
    for payload in [{'logo':'javascript:alert(1)'},{'logo':'data:image/svg+xml;base64,PHN2Zz4='},{'accent':'#000000'},{'name':'  '}]:
        with pytest.raises(ValidationError):Branding(**payload)
    assert Branding(name=' Example ').name=='Example'


def test_team_invitation_role_and_project_isolation(monkeypatch):
    from app import edition,licensing,business_routes
    from app.commercial import workspaces
    from app.main import app
    from app.projects import resolve_project
    monkeypatch.setattr(edition,'get_edition',lambda:'commercial')
    monkeypatch.setattr(business_routes,'get_edition',lambda:'commercial')
    monkeypatch.setattr(licensing,'require_commercial_license',lambda:None)
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
        login=client.post('/api/v1/mobile/login',json={'username':username,'password':'team-member-test-password'})
        headers={'Authorization':'Bearer '+login.json()['token'],'X-Engram-Project':project}
        items=client.get('/api/v1/projects',headers=headers).json()
        assert [str(item['id']) for item in items]==[project]
        assert client.get('/api/v1/memories',headers=headers).status_code==200
        assert client.post('/api/v1/memories',headers=headers,json={'title':'No','content':'Viewer cannot edit'}).status_code==403
        assert client.get('/api/v1/memories',headers={**headers,'X-Engram-Project':DEFAULT_PROJECT_ID}).status_code==404
        assert client.post('/api/v1/team/invitations',headers=headers,json={'username':'outsider','role':'owner'}).status_code==403
        with connect() as conn:
            member=conn.execute('SELECT id FROM users WHERE username=%s',(username,)).fetchone()['id']
        bound=Principal('oauth',str(member),username,False,{'memory:write','memory:read','mcp:use'},'oauth',project)
        assert resolve_project(bound,project)==project
        assert 'memory:write' not in bound.scopes
        with project_scope(project):workspaces.set_member(principal,username,None)
        assert client.get('/api/v1/memories',headers=headers).status_code==404
        with pytest.raises(HTTPException):resolve_project(bound,project)
    finally:
        with connect() as conn:
            conn.execute('DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username IN (%s,%s))',(username,'owner-'+unique))
            conn.execute('DELETE FROM projects WHERE id=%s',(project,))
            conn.execute('DELETE FROM users WHERE username IN (%s,%s)',(username,'owner-'+unique));conn.commit()
