import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from owner import service
from uuid import uuid4
from datetime import date,timedelta

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('OWNER_DATABASE',str(tmp_path/'orders.sqlite'))
    password=tmp_path/'password';password.write_text('owner-test-password')
    monkeypatch.setenv('OWNER_PASSWORD_FILE',str(password))
    private=Ed25519PrivateKey.generate()
    key=tmp_path/'private.pem';key.write_bytes(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    monkeypatch.setenv('ISSUER_PRIVATE_KEY_FILE',str(key))
    client=TestClient(service.app)
    auth=('owner','owner-test-password')
    response=client.get('/orders',auth=auth)
    return client,auth,{'X-Owner-CSRF':response.json()['csrf']}

def test_order_approval_idempotent_and_delivery_retry(setup,monkeypatch):
    client,auth,headers=setup
    assert client.get('/orders').status_code==401
    response=client.post('/orders',json={'customer':'Example Ltd','email':'jayden@hindley.tech','installation_id':str(uuid4())})
    identifier=response.json()['id']
    assert client.post(f'/orders/{identifier}/resend',auth=auth,headers=headers).status_code==409
    assert service.deliver_one() is False
    expiry=(date.today()+timedelta(days=7)).isoformat()
    assert client.post(f'/orders/{identifier}/paid',auth=auth,json={'expires':expiry}).status_code==403
    for _ in range(2):
        assert client.post(f'/orders/{identifier}/paid',auth=auth,headers=headers,json={'expires':expiry}).status_code==200
        with service.database() as db:
            current=db.execute('SELECT license_key FROM orders').fetchone()[0]
        if _==0: original=current
        else: assert original==current
    assert original not in client.get('/orders',auth=auth).text
    def fail(row): raise OSError('private smtp response')
    monkeypatch.setattr(service,'send_email',fail)
    assert service.deliver_one()
    with service.database() as db:
        row=db.execute('SELECT * FROM orders').fetchone()
        assert row['mail_state']=='error' and row['last_error']=='OSError'
        assert row['license_key']==original
    assert client.post(f'/orders/{identifier}/resend',auth=auth,headers=headers).status_code==200
    delivered=[]
    monkeypatch.setattr(service,'send_email',lambda row:delivered.append(row['license_key']))
    assert service.deliver_one()
    assert delivered==[original]
    assert not service.deliver_one()

def test_invalid_request_never_issues_key(setup):
    client,auth,headers=setup
    for email in ['bad','x@example.com\r\nBcc: victim@example.com']:
        assert client.post('/orders',json={'customer':'Example','email':email,'installation_id':str(uuid4())}).status_code==422
    assert client.get('/orders',auth=auth).json()['orders']==[]
    public=client.get('/public-key')
    assert public.status_code==200 and 'BEGIN PUBLIC KEY' in public.text
    assert 'PRIVATE KEY' not in public.text


def test_sender_and_customer_recipient_are_separate(monkeypatch):
    captured = {}
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, username, password): captured['username'] = username
        def send_message(self, message): captured['message'] = message
    monkeypatch.setattr(service.smtplib, 'SMTP_SSL', SMTP)
    monkeypatch.setattr(service, 'secret', lambda name: 'test-password')
    monkeypatch.setenv('SMTP_SENDER', 'jayden@hindley.tech')
    monkeypatch.setenv('SMTP_USERNAME', 'jayden@hindley.tech')
    service.send_email({'id': str(uuid4()), 'customer': 'Customer Ltd',
                        'email': 'customer@example.com', 'installation_id': str(uuid4()),
                        'expires': '2026-12-31', 'license_key': 'test-key'})
    assert captured['username'] == 'jayden@hindley.tech'
    assert captured['message']['From'] == 'jayden@hindley.tech'
    assert captured['message']['To'] == 'customer@example.com'


def test_renewal_replaces_once_and_suppresses_old_notices(setup,monkeypatch):
    client,auth,headers=setup
    order=client.post('/orders',json={'customer':'Renewal Ltd','email':'customer@example.com','installation_id':str(uuid4())}).json()['id']
    expiry=date.today()+timedelta(days=7)
    assert client.post(f'/orders/{order}/paid',auth=auth,headers=headers,json={'expires':expiry.isoformat()}).status_code==200
    for _ in range(2):service.queue_expiry_notices(today=date.today())
    with service.database() as db:
        assert db.execute('SELECT count(*) FROM renewal_notices').fetchone()[0]==1
    replacement_expiry=expiry+timedelta(days=60)
    responses=[client.post(f'/orders/{order}/renew',auth=auth,headers=headers,json={'expires':replacement_expiry.isoformat()}) for _ in range(2)]
    assert all(r.status_code==200 for r in responses)
    assert responses[0].json()['id']==responses[1].json()['id']
    with service.database() as db:
        rows=db.execute('SELECT * FROM orders ORDER BY created').fetchall()
        assert len(rows)==2 and rows[0]['license_key']!=rows[1]['license_key']
        assert rows[1]['renewal_of']==order
    monkeypatch.setattr(service,'send_email',lambda row:pytest.fail('Old licence must not get expiry notices'))
    assert service.deliver_notice() is False
