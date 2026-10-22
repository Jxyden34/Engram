"""Commercial business endpoints; see LICENSE-COMMERCIAL."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from pydantic import field_validator
from app import licensing
from app.edition import get_edition
from app.security import authenticate, require
from app.audit import log
from app.database import connect,current_project_id
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse,Response
from app.config import settings
from app.security import hash_password
from pathlib import Path
import hmac
import httpx

router=APIRouter(prefix='/api/v1')


def instance_admin(request):
    p=authenticate(request)
    if not p.is_admin or p.auth_type not in {'session','mobile'}:raise HTTPException(403,'Instance administrator required')
    return p


@router.get('/setup/status')
def setup_status():
    if get_edition()!='commercial':return {'available':False}
    with connect() as conn:
        exists=conn.execute('SELECT 1 FROM users LIMIT 1').fetchone() is not None
        row=conn.execute('SELECT completed_at FROM instance_setup WHERE singleton').fetchone()
    return {'available':True,'needs_admin':not exists,'bootstrap_enabled':Path(settings().setup_bootstrap_token_file).is_file(),'completed_at':row['completed_at']}


class Bootstrap(BaseModel):
    username:str=Field(min_length=3,max_length=254,pattern=r'^\S+$')
    password:str=Field(min_length=12,max_length=256)
    token:str=Field(min_length=32,max_length=256)


@router.post('/setup/bootstrap',status_code=201)
def bootstrap(body:Bootstrap):
    if get_edition()!='commercial':raise HTTPException(404,'Commercial setup only')
    try:expected=Path(settings().setup_bootstrap_token_file).read_text().strip()
    except OSError:raise HTTPException(403,'Bootstrap is disabled. Create an administrator using the local CLI.')
    if len(expected)<32 or not hmac.compare_digest(expected.encode(),body.token.encode()):raise HTTPException(403,'Invalid setup token')
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(370006)')
        if conn.execute('SELECT 1 FROM users LIMIT 1').fetchone():raise HTTPException(409,'Setup account creation is closed. Sign in with an existing account.')
        conn.execute('INSERT INTO users(username,password_hash,is_admin) VALUES(%s,%s,true)',(body.username,hash_password(body.password)));conn.commit()
    return {'username':body.username}


def installed_models():
    try:
        response=httpx.get(settings().ollama_url.rstrip('/')+'/api/tags',timeout=10)
        response.raise_for_status()
        return [str(item['name']) for item in response.json()['models']]
    except (httpx.HTTPError,ValueError,KeyError,TypeError) as exc:raise HTTPException(503,'Ollama is unavailable. Check the configured server and its models.') from exc


@router.get('/setup/models')
def setup_models(request:Request):
    commercial();instance_admin(request)
    from app.preferences import chat_model
    return {'installed':installed_models(),'chat_model':chat_model(),'embedding_model':settings().embedding_model}


class ModelChoice(BaseModel):
    model:str=Field(min_length=1,max_length=200)


@router.put('/setup/models')
def setup_model(body:ModelChoice,request:Request):
    commercial();p=instance_admin(request)
    if body.model not in installed_models():raise HTTPException(422,'Choose a model already installed on the configured Ollama server')
    with connect() as conn:
        conn.execute('UPDATE instance_setup SET chat_model=%s WHERE singleton',(body.model,));conn.commit()
    log(p.actor,'setup.model_selected','installation',request=request,new_data={'model':body.model})
    return {'model':body.model}


@router.post('/setup/finish')
def setup_finish(request:Request):
    commercial();p=instance_admin(request)
    from app.preferences import chat_model
    names=installed_models()
    def present(model):return model in names or model+':latest' in names
    if not present(chat_model()) or not present(settings().embedding_model):raise HTTPException(409,'Install the configured chat and embedding models before finishing setup')
    with connect() as conn:
        conn.execute('UPDATE instance_setup SET completed_at=now() WHERE singleton');conn.commit()
    log(p.actor,'setup.completed','installation',request=request)
    return {'ok':True}


@router.get('/handover')
def handover(request:Request,format:Literal['json','markdown']='json'):
    commercial();p=require(request,'memory:read')
    from app.commercial import handover as exporter
    result=exporter.snapshot()
    log(p.actor,'handover.exported','project',current_project_id(),request,new_data={'format':format,'count':result['exported_memories']})
    headers={'Content-Disposition':f'attachment; filename="engram-handover.{"json" if format=="json" else "md"}"','Cache-Control':'no-store'}
    if format=='markdown':return Response(exporter.markdown(result),media_type='text/markdown',headers=headers)
    return JSONResponse(jsonable_encoder(result),headers=headers)


def commercial():
    if get_edition()!='commercial':
        raise HTTPException(404,'This feature is available in the Commercial build')
    licensing.require_commercial_license()


class Branding(BaseModel):
    name:str=Field(default='Engram',min_length=1,max_length=80)
    tagline:str=Field(default='private cognition layer',max_length=160)
    accent:str=Field(default='#b6ff4a',pattern=r'^#[0-9a-fA-F]{6}$')
    logo:str=Field(default='',max_length=140000)

    @field_validator('name')
    @classmethod
    def nonblank_name(cls,value):
        if not value.strip():raise ValueError('Choose a company name')
        return value.strip()

    @field_validator('accent')
    @classmethod
    def readable_accent(cls,value):
        rgb=[int(value[i:i+2],16)/255 for i in (1,3,5)]
        linear=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]
        luminance=sum(v*w for v,w in zip(linear,[0.2126,0.7152,0.0722]))
        if (luminance+0.05)/0.055<4.5:raise ValueError('Choose a brighter accent for readable buttons and labels')
        return value

    @field_validator('logo')
    @classmethod
    def safe_logo(cls,value):
        import base64,binascii
        if not value:return value
        if not value.startswith('data:image/png;base64,'):raise ValueError('Use a PNG logo')
        try:data=base64.b64decode(value.split(',',1)[1],validate=True)
        except (ValueError,binascii.Error):raise ValueError('Invalid PNG data')
        if len(data)>100000 or not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Use a PNG smaller than 100 KB')
        return value


@router.get('/branding')
def branding():
    if get_edition()!='commercial':return Branding().model_dump()
    with connect() as conn:
        return dict(conn.execute('SELECT name,tagline,accent,logo FROM instance_branding WHERE singleton').fetchone())


@router.put('/branding')
def update_branding(body:Branding,request:Request):
    commercial()
    p=authenticate(request)
    if not p.is_admin or p.auth_type not in {'session','mobile'}:raise HTTPException(403,'Instance administrator required')
    with connect() as conn:
        conn.execute('UPDATE instance_branding SET name=%s,tagline=%s,accent=%s,logo=%s WHERE singleton',
                     (body.name.strip(),body.tagline,body.accent,body.logo));conn.commit()
    log(p.actor,'branding.updated','installation',request=request,new_data={'name':body.name})
    return body.model_dump()


class Member(BaseModel):
    username: str=Field(min_length=3,max_length=254,pattern=r'^\S+$')
    role: Literal['owner','editor','viewer'] | None='viewer'


class InvitationAccept(BaseModel):
    token: str=Field(min_length=30,max_length=200)
    password: str=Field(min_length=12,max_length=256)


@router.get('/team/members')
def team_members(request:Request):
    commercial()
    from app.commercial import workspaces
    return workspaces.members(authenticate(request))


@router.post('/team/invitations',status_code=201)
def team_invite(body:Member,request:Request):
    commercial()
    if body.role is None: raise HTTPException(422,'Choose an invitation role')
    from app.commercial import workspaces
    p=authenticate(request)
    result=workspaces.invite(p,body.username,body.role)
    log(p.actor,'team.invited','project',current_project_id(),request,new_data={'username':body.username,'role':body.role})
    return result


@router.post('/team/accept')
def team_accept(body:InvitationAccept):
    commercial()
    from app.commercial import workspaces
    return workspaces.accept(body.token,body.password)


@router.put('/team/members')
def team_member(body:Member,request:Request):
    commercial()
    from app.commercial import workspaces
    p=authenticate(request)
    result=workspaces.set_member(p,body.username,body.role)
    log(p.actor,'team.member_changed','project',current_project_id(),request,new_data=body.model_dump())
    return result


@router.get('/team/activity')
def team_activity(request:Request):
    commercial();require(request,'memory:read')
    with connect() as conn:
        return [dict(r) for r in conn.execute('SELECT actor,action,entity_type,created_at FROM audit_log ORDER BY created_at DESC LIMIT 50').fetchall()]
