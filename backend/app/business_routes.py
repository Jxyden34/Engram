"""Commercial endpoints remain discoverable but unavailable in Personal builds."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from app import licensing
from app.edition import get_edition
from app.security import authenticate, require
from app.audit import log
from app.database import connect,current_project_id

router=APIRouter(prefix='/api/v1')


def commercial():
    if get_edition()!='commercial':
        raise HTTPException(404,'This feature is available in the Commercial build')
    licensing.require_commercial_license()


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
