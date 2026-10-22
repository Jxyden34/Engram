"""Owner-operated licence orders, manual payment confirmation, durable email delivery."""
import hashlib
import hmac
import os
import re
import smtplib
import sqlite3
import ssl
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import date,datetime,timezone
from email.message import EmailMessage
from pathlib import Path
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, field_validator
from scripts.commercial_license import issue


def secret(name):
    return Path(os.environ[name]).read_text().strip()


@contextmanager
def database():
    with sqlite3.connect(os.environ.get("OWNER_DATABASE", "/data/orders.sqlite"), timeout=30) as db:
        db.row_factory = sqlite3.Row
        db.execute("""CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY, customer TEXT, email TEXT, installation_id TEXT,
            created REAL, source TEXT, paid REAL, expires TEXT, license_key TEXT,
            mail_state TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0,
            next_attempt REAL DEFAULT 0, sent REAL, last_error TEXT)""")
        columns={row[1] for row in db.execute('PRAGMA table_info(orders)')}
        for name,kind in [('renewal_of','TEXT'),('kind',"TEXT DEFAULT 'new'")]:
            if name not in columns:db.execute(f'ALTER TABLE orders ADD COLUMN {name} {kind}')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS renewal_once ON orders(renewal_of,expires) WHERE renewal_of IS NOT NULL')
        db.execute("CREATE TABLE IF NOT EXISTS renewal_notices(id TEXT PRIMARY KEY,order_id TEXT NOT NULL,stage INTEGER NOT NULL,mail_state TEXT DEFAULT 'pending',next_attempt REAL DEFAULT 0,attempts INTEGER DEFAULT 0,last_error TEXT,UNIQUE(order_id,stage))")
        yield db


basic = HTTPBasic()


def owner(credentials: HTTPBasicCredentials = Depends(basic)):
    valid_user = hmac.compare_digest(credentials.username.encode(), os.environ.get("OWNER_USERNAME", "owner").encode())
    valid_password = hmac.compare_digest(credentials.password.encode(), secret("OWNER_PASSWORD_FILE").encode())
    if not (valid_user and valid_password):
        raise HTTPException(401, "Owner login required", headers={"WWW-Authenticate": "Basic"})
    return hmac.new(secret("OWNER_PASSWORD_FILE").encode(), b"engram-owner-csrf", hashlib.sha256).hexdigest()


def mutation(token=Depends(owner), x_owner_csrf: str = Header(default="")):
    if not hmac.compare_digest(token, x_owner_csrf):
        raise HTTPException(403, "Refresh the owner dashboard before making changes")


class Order(BaseModel):
    customer: str = Field(min_length=1, max_length=200)
    email: str = Field(max_length=254)
    installation_id: UUID
    renewal: bool=False

    @field_validator("customer", "email")
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("Provide text without control characters")
        return value

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", value):
            raise ValueError("Provide a valid email address")
        return value


class Approval(BaseModel):
    expires: date


def send_email(row):
    message = EmailMessage()
    sender = os.environ.get("SMTP_SENDER", "jayden@hindley.tech")
    message["From"] = sender
    message["To"] = row["email"]
    reminder=isinstance(row,dict) and row.get('_kind')=='reminder'
    message["Subject"] = "Your Engram licence expires soon" if reminder else "Your Engram Commercial licence key"
    message["Message-ID"] = f"<engram-licence-{row['id']}@{sender.split('@')[1]}>"
    message.set_content(
        f"Hello {row['customer']},\n\nYour Engram Commercial licence is ready.\n"
        f"Installation: {row['installation_id']}\nValid through: {row['expires']} (UTC)\n\n"
        f"{row['license_key']}\n\nOpen Licence in your Engram installation, sign in as an administrator, "
        "and paste this key to activate. Keep this email for your records.\n\n"
        "Questions? Reply to this email.\nJayden\n")
    if reminder:
        message.set_content(f"Hello {row['customer']},\n\nYour Engram Commercial licence expires on {row['expires']} (UTC).\nInstallation: {row['installation_id']}\n\nOpen Licence in your workspace to request renewal, or reply to this email. No automatic payment was taken.\n\nJayden\n")
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "box.hindley.tech"),
                          int(os.environ.get("SMTP_PORT", "465")), timeout=30,
                          context=ssl.create_default_context()) as smtp:
        smtp.login(os.environ.get("SMTP_USERNAME", sender), secret("SMTP_PASSWORD_FILE"))
        smtp.send_message(message)


def deliver_one():
    now = time.time()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("""SELECT * FROM orders WHERE license_key IS NOT NULL
            AND mail_state != 'sent' AND next_attempt <= ? ORDER BY created LIMIT 1""", (now,)).fetchone()
        if row is None:
            return False
        # Durable lease: a restart retries the same key after five minutes.
        db.execute("UPDATE orders SET mail_state='sending', attempts=attempts+1, next_attempt=? WHERE id=?",
                   (now + 300, row["id"]))
        db.commit()
    try:
        send_email(row)
    except Exception as exc:
        # Exception text can contain SMTP credentials or recipient data; store only its type.
        with database() as db:
            db.execute("UPDATE orders SET mail_state='error', last_error=?, next_attempt=? WHERE id=?",
                       (type(exc).__name__, now + min(3600, 30 * 2 ** min(row["attempts"], 7)), row["id"]))
    else:
        with database() as db:
            db.execute("UPDATE orders SET mail_state='sent', sent=?, last_error=NULL WHERE id=?", (time.time(), row["id"]))
    return True


@asynccontextmanager
async def lifespan(app):
    stop = threading.Event()
    def run():
        while not stop.is_set():
            try:
                deliver_one()
                queue_expiry_notices()
                deliver_notice()
            except Exception:
                pass  # A transient database failure must not stop subsequent deliveries.
            stop.wait(5)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    yield
    stop.set()
    thread.join(timeout=35)


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/")
def storefront():
    return FileResponse(Path(__file__).with_name("index.html"))


@app.get("/admin")
def dashboard(token=Depends(owner)):
    return FileResponse(Path(__file__).with_name("admin.html"), headers={"Cache-Control": "no-store"})


@app.get("/orders")
def orders(token=Depends(owner)):
    with database() as db:
        rows = db.execute("""SELECT id,customer,email,installation_id,created,paid,expires,kind,renewal_of,
            mail_state,attempts,sent,last_error FROM orders ORDER BY created DESC LIMIT 200""").fetchall()
    return {"csrf": token, "orders": [dict(row) for row in rows]}


@app.post("/orders", status_code=201)
def request_key(order: Order, request: Request):
    source = request.client.host if request.client else "unknown"
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        count = db.execute("SELECT count(*) FROM orders WHERE source=? AND created>?", (source, time.time()-86400)).fetchone()[0]
        if count >= 20:
            raise HTTPException(429, "Too many requests; contact the owner for assistance")
        identifier = str(uuid4())
        db.execute("INSERT INTO orders(id,customer,email,installation_id,created,source,kind) VALUES(?,?,?,?,?,?,?)",
                   (identifier, order.customer, order.email, str(order.installation_id), time.time(), source, "renewal_request" if order.renewal else "new"))
    return {"id": identifier, "message": "Request received. The owner will arrange payment separately; no payment was taken."}


@app.post("/orders/{identifier}/paid", dependencies=[Depends(mutation)])
def mark_paid(identifier: UUID, approval: Approval):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM orders WHERE id=?", (str(identifier),)).fetchone()
        if row is None:
            raise HTTPException(404, "Order not found")
        if not row["license_key"]:
            try:
                private = serialization.load_pem_private_key(Path(os.environ["ISSUER_PRIVATE_KEY_FILE"]).read_bytes(), password=None)
                key = issue(private, row["installation_id"], row["customer"], approval.expires)
            except ValueError as exc:
                raise HTTPException(400, "Provide a current or future expiry date and a valid issuer key") from exc
            db.execute("UPDATE orders SET paid=?, expires=?, license_key=?, next_attempt=0 WHERE id=?",
                       (time.time(), approval.expires.isoformat(), key, str(identifier)))
    return {"state": "queued", "message": "Payment confirmed; the licence email is queued. Repeating confirmation never issues another key."}


@app.post("/orders/{identifier}/resend", dependencies=[Depends(mutation)])
def resend(identifier: UUID):
    with database() as db:
        row = db.execute("SELECT * FROM orders WHERE id=?", (str(identifier),)).fetchone()
        if not row or not row["license_key"]:
            raise HTTPException(409, "Confirm payment before sending a key")
        if row["mail_state"] == "sending" and row["next_attempt"] > time.time():
            raise HTTPException(409, "Delivery is already in progress")
        db.execute("UPDATE orders SET mail_state='pending', next_attempt=0 WHERE id=?", (str(identifier),))
    return {"state": "queued"}


@app.post('/orders/{identifier}/renew',dependencies=[Depends(mutation)])
def renew(identifier:UUID,approval:Approval):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM orders WHERE id=?',(str(identifier),)).fetchone()
        if not row or not row['license_key']:raise HTTPException(409,'Only an issued licence can be renewed')
        if approval.expires<=date.fromisoformat(row['expires']):raise HTTPException(400,'Renewal must extend the expiry date')
        existing=db.execute('SELECT id FROM orders WHERE renewal_of=? AND expires=?',(str(identifier),approval.expires.isoformat())).fetchone()
        if existing:return {'id':existing['id'],'state':'queued'}
        if db.execute('SELECT 1 FROM orders WHERE renewal_of=?',(str(identifier),)).fetchone():
            raise HTTPException(409,'Renew the most recent replacement order instead')
        private=serialization.load_pem_private_key(Path(os.environ['ISSUER_PRIVATE_KEY_FILE']).read_bytes(),password=None)
        try:key=issue(private,row['installation_id'],row['customer'],approval.expires)
        except ValueError as exc:raise HTTPException(400,'Choose a current or future expiry date') from exc
        new_id=str(uuid4())
        db.execute('''INSERT INTO orders(id,customer,email,installation_id,created,source,paid,expires,license_key,renewal_of,kind)
            VALUES(?,?,?,?,?,?,?,?,?,?,'renewal')''',(new_id,row['customer'],row['email'],row['installation_id'],time.time(),'owner',time.time(),approval.expires.isoformat(),key,str(identifier)))
    return {'id':new_id,'state':'queued','message':'Renewal confirmed; replacement key email queued'}


def queue_expiry_notices(today=None):
    today=today or datetime.now(timezone.utc).date()
    with database() as db:
        rows=db.execute('''SELECT * FROM orders o WHERE license_key IS NOT NULL AND expires IS NOT NULL
            AND NOT EXISTS(SELECT 1 FROM orders child WHERE child.renewal_of=o.id)''').fetchall()
        for row in rows:
            days=(date.fromisoformat(row['expires'])-today).days
            if 0<=days<=30:
                stage=min(n for n in [1,7,30] if days<=n)
                db.execute('INSERT OR IGNORE INTO renewal_notices(id,order_id,stage) VALUES(?,?,?)',
                           (str(uuid4()),row['id'],stage))


def deliver_notice():
    now=time.time()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('''SELECT n.id AS notice_id,n.attempts AS notice_attempts,o.* FROM renewal_notices n JOIN orders o ON o.id=n.order_id
            WHERE n.mail_state!='sent' AND n.next_attempt<=?
            AND NOT EXISTS(SELECT 1 FROM orders child WHERE child.renewal_of=o.id)
            ORDER BY n.next_attempt LIMIT 1''',(now,)).fetchone()
        if not row:return False
        db.execute("UPDATE renewal_notices SET mail_state='sending',next_attempt=?,attempts=attempts+1 WHERE id=?",(now+300,row['notice_id']));db.commit()
    try:send_email({**dict(row),'id':row['notice_id'],'_kind':'reminder'})
    except Exception as exc:
        with database() as db:
            db.execute("UPDATE renewal_notices SET mail_state='error',last_error=?,next_attempt=? WHERE id=?",
                       (type(exc).__name__,now+min(3600,30*2**min(row['notice_attempts'],7)),row['notice_id']))
    else:
        with database() as db:db.execute("UPDATE renewal_notices SET mail_state='sent',last_error=NULL WHERE id=?",(row['notice_id'],))
    return True
