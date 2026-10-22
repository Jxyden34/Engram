"""Commercial project membership; see LICENSE-COMMERCIAL."""
import secrets
from fastapi import HTTPException
from app.database import connect, DEFAULT_PROJECT_ID, current_project_id
from app.security import hash_password, sha256


def role(principal, project_id):
    if principal.auth_type not in {'session','mobile'}:
        with connect() as conn:
            user=conn.execute('SELECT is_admin,team_only FROM users WHERE id=%s AND is_active',(principal.user_id,)).fetchone()
        if not user: return None
        if user['is_admin']: return 'owner'
        team_only=user['team_only']
    else:
        team_only=principal.team_only
    if principal.is_admin:
        return 'owner'
    with connect() as conn:
        row = conn.execute('SELECT role FROM project_members WHERE project_id=%s AND user_id=%s',
                           (project_id, principal.user_id)).fetchone()
    if row:
        return row['role']
    if project_id == DEFAULT_PROJECT_ID and not team_only:
        return 'editor'
    return None


def manage(principal):
    if principal.auth_type not in {'session','mobile'} or role(principal,current_project_id()) != 'owner':
        raise HTTPException(403,'Project owner required')


def members(principal):
    manage(principal)
    with connect() as conn:
        rows=conn.execute('''SELECT u.id,u.username,m.role FROM project_members m JOIN users u ON u.id=m.user_id
                            WHERE m.project_id=%s ORDER BY u.username''',(current_project_id(),)).fetchall()
    return [dict(row) for row in rows]


def invite(principal,username,member_role):
    manage(principal)
    token=secrets.token_urlsafe(32)
    with connect() as conn:
        if conn.execute('SELECT 1 FROM users WHERE username=%s',(username,)).fetchone():
            raise HTTPException(409,'Account exists. Add that username as an existing member instead.')
        row=conn.execute('''INSERT INTO team_invitations(project_id,username,role,token_hash)
            VALUES(%s,%s,%s,%s) RETURNING id,expires_at''',
            (current_project_id(),username,member_role,sha256(token))).fetchone()
        conn.commit()
    return {**dict(row),'token':token}


def accept(token,password):
    with connect() as conn:
        row=conn.execute('''SELECT * FROM team_invitations WHERE token_hash=%s
            AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>now() FOR UPDATE''',(sha256(token),)).fetchone()
        if not row:
            raise HTTPException(410,'Invitation expired or already used')
        if conn.execute('SELECT 1 FROM users WHERE username=%s',(row['username'],)).fetchone():
            raise HTTPException(409,'Account already exists. Ask the project owner to add your existing account.')
        user=conn.execute('INSERT INTO users(username,password_hash,team_only) VALUES(%s,%s,true) RETURNING id',
                          (row['username'],hash_password(password))).fetchone()
        conn.execute('INSERT INTO project_members(project_id,user_id,role) VALUES(%s,%s,%s)',
                     (row['project_id'],user['id'],row['role']))
        conn.execute('UPDATE team_invitations SET accepted_at=now() WHERE id=%s',(row['id'],))
        conn.commit()
    return {'username':row['username'],'project_id':str(row['project_id'])}


def set_member(principal,username,member_role):
    manage(principal)
    with connect() as conn:
        conn.execute('SELECT id FROM projects WHERE id=%s FOR UPDATE',(current_project_id(),))
        user=conn.execute('SELECT id FROM users WHERE username=%s AND is_active',(username,)).fetchone()
        if not user:
            raise HTTPException(404,'Active account not found')
        old=conn.execute('SELECT role FROM project_members WHERE project_id=%s AND user_id=%s',
                         (current_project_id(),user['id'])).fetchone()
        if old and old['role']=='owner' and member_role!='owner' and not principal.is_admin:
            count=conn.execute("SELECT count(*) AS n FROM project_members WHERE project_id=%s AND role='owner'",
                               (current_project_id(),)).fetchone()['n']
            if count<=1:
                raise HTTPException(409,'Keep at least one project owner')
        if member_role is None:
            conn.execute('DELETE FROM project_members WHERE project_id=%s AND user_id=%s',(current_project_id(),user['id']))
        else:
            conn.execute('''INSERT INTO project_members(project_id,user_id,role) VALUES(%s,%s,%s)
                ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role''',
                (current_project_id(),user['id'],member_role))
        conn.commit()
    return {'ok':True}
