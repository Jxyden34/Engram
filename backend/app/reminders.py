"""Private in-app memory reminders for both editions."""
from datetime import datetime,timedelta,timezone
from uuid import UUID
from typing import Literal
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,Field,field_validator
from app.database import connect
from app.security import require

router=APIRouter(prefix='/api/v1/reminders')


class Reminder(BaseModel):
    memory_id:UUID
    due_at:datetime
    note:str=Field(default='',max_length=1000)

    @field_validator('due_at')
    @classmethod
    def future(cls,value):
        now=datetime.now(timezone.utc)
        if value.tzinfo is None or not now<value<=now+timedelta(days=365*5):raise ValueError('Choose a future time within five years, including a timezone')
        return value


class ReminderChange(BaseModel):
    status:Literal['pending','done','dismissed']='pending'
    due_at:datetime|None=None

    @field_validator('due_at')
    @classmethod
    def future(cls,value):return Reminder.future(value) if value else None


def user(request):
    p=require(request,'memory:read')
    if not p.user_id or p.auth_type not in {'session','mobile'}:raise HTTPException(403,'Sign in to manage your reminders')
    return p


@router.get('')
def list_reminders(request:Request,due_only:bool=False):
    p=user(request)
    with connect() as conn:
        return [dict(r) for r in conn.execute('''SELECT r.*,m.title FROM memory_reminders r JOIN memories m ON m.id=r.memory_id
            WHERE r.user_id=%s AND r.status='pending' AND m.deleted_at IS NULL AND (NOT %s OR r.due_at<=now())
            ORDER BY r.due_at,r.id LIMIT 500''',(p.user_id,due_only)).fetchall()]


@router.post('',status_code=201)
def create_reminder(body:Reminder,request:Request):
    p=user(request)
    with connect() as conn:
        if not conn.execute('SELECT id FROM memories WHERE id=%s AND deleted_at IS NULL',(str(body.memory_id),)).fetchone():raise HTTPException(404,'Memory not found in this project')
        conn.execute('''INSERT INTO memory_reminders(user_id,memory_id,note,due_at) VALUES(%s,%s,%s,%s)
            ON CONFLICT(user_id,memory_id,due_at) DO NOTHING''',(p.user_id,str(body.memory_id),body.note,body.due_at))
        row=conn.execute('SELECT * FROM memory_reminders WHERE user_id=%s AND memory_id=%s AND due_at=%s',(p.user_id,str(body.memory_id),body.due_at)).fetchone();conn.commit()
    return dict(row)


@router.patch('/{identifier}')
def update_reminder(identifier:UUID,body:ReminderChange,request:Request):
    p=user(request)
    with connect() as conn:
        row=conn.execute('''UPDATE memory_reminders SET status=%s,due_at=COALESCE(%s,due_at)
            WHERE id=%s AND user_id=%s RETURNING *''',(body.status,body.due_at,str(identifier),p.user_id)).fetchone()
        if not row:raise HTTPException(404,'Reminder not found')
        conn.commit()
    return dict(row)
