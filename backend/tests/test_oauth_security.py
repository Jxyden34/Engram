"""OAuth security regressions against the disposable PostgreSQL test database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4
import json

import pytest
from fastapi import HTTPException

from app import oauth
from app.database import connect, project_scope
from app.security import sha256


@pytest.fixture(autouse=True)
def database_deadlines(monkeypatch):
    def bounded_connect():
        conn = connect()
        conn.execute("SET LOCAL lock_timeout='5s'")
        conn.execute("SET LOCAL statement_timeout='10s'")
        return conn
    monkeypatch.setattr(oauth, 'connect', bounded_connect)


@pytest.fixture
def grant():
    name = 'oauth-security-' + uuid4().hex
    with connect() as conn:
        user = str(conn.execute("INSERT INTO users(username,password_hash) VALUES (%s,'unused-test-hash') RETURNING id",
                                (name,)).fetchone()['id'])
        project = str(conn.execute("INSERT INTO projects(slug,name) VALUES (%s,'OAuth security test') RETURNING id",
                                   (name,)).fetchone()['id'])
        conn.commit()
    client = oauth.create_static_client(name, ['http://localhost/callback'],
                                        sorted(oauth.OAUTH_SCOPES), 'test', user)['client_id']
    data = {'client_id': client, 'user_id': user, 'project_id': project,
            'resource': oauth.mcp_resource(), 'redirect_uri': 'http://localhost/callback',
            'code_verifier': 'v' * 43}
    try:
        yield data
    finally:
        with connect() as conn:
            conn.execute('DELETE FROM oauth_clients WHERE client_id=%s', (client,))
            conn.execute('DELETE FROM users WHERE id=%s', (user,))
            conn.execute('DELETE FROM projects WHERE id=%s', (project,))
            conn.commit()


def code_form(grant, scopes=None):
    with project_scope(grant['project_id']):
        code = oauth.create_authorization_code(grant['client_id'], grant['user_id'], grant['redirect_uri'],
            scopes or ['mcp:use', 'memory:read', 'memory:write'], grant['resource'],
            oauth._pkce_s256(grant['code_verifier']))
    return {**grant, 'code': code}


def tokens(grant):
    response = oauth.exchange_authorization_code(code_form(grant))
    assert response.status_code == 200
    return json.loads(response.body)


def refresh_form(grant, pair):
    return {'client_id': grant['client_id'], 'resource': grant['resource'],
            'refresh_token': pair['refresh_token']}


def consent_id(grant):
    with connect() as conn:
        return str(conn.execute('SELECT id FROM oauth_consents WHERE client_id=%s',
                                (grant['client_id'],)).fetchone()['id'])


def test_revoked_codes_never_revive_when_consent_is_renewed(grant):
    old = code_form(grant)
    oauth.revoke_consent(consent_id(grant))
    assert oauth.exchange_authorization_code(old).status_code == 400
    fresh = code_form(grant)
    assert oauth.exchange_authorization_code(old).status_code == 400
    response = oauth.exchange_authorization_code(fresh)
    pair = json.loads(response.body)
    principal = oauth.oauth_access_token_principal(pair['access_token'], grant['resource'])
    assert principal and principal.project_id == grant['project_id']
    oauth.revoke_consent(consent_id(grant))
    assert oauth.oauth_access_token_principal(pair['access_token']) is None
    assert oauth.exchange_refresh_token(refresh_form(grant, pair)).status_code == 400


def test_code_pkce_binding_and_refresh_scope_narrowing_remain_intact(grant):
    form = code_form(grant)
    assert oauth.exchange_authorization_code({**form, 'code_verifier': 'wrong'}).status_code == 400
    with pytest.raises(HTTPException) as wrong_redirect:
        oauth.exchange_authorization_code({**form, 'redirect_uri': 'http://localhost/other'})
    assert wrong_redirect.value.status_code == 400
    # An unsuccessful PKCE exchange must not consume the valid code.
    response = oauth.exchange_authorization_code(form)
    assert response.status_code == 200
    pair = json.loads(response.body)
    assert oauth.exchange_authorization_code(form).status_code == 400
    narrowed = oauth.exchange_refresh_token({**refresh_form(grant, pair), 'scope': 'mcp:use memory:read'})
    assert narrowed.status_code == 200
    child = json.loads(narrowed.body)
    principal = oauth.oauth_access_token_principal(child['access_token'], grant['resource'])
    assert principal.scopes == {'mcp:use', 'memory:read'}
    assert principal.project_id == grant['project_id']
    assert oauth.exchange_refresh_token({**refresh_form(grant, child), 'scope': 'memory:write'}).status_code == 400


@pytest.mark.parametrize('kind', ['code', 'refresh'])
def test_failed_descendant_insert_rolls_back_parent_and_partial_children(grant, monkeypatch, kind):
    form = code_form(grant) if kind == 'code' else refresh_form(grant, tokens(grant))
    exchange = oauth.exchange_authorization_code if kind == 'code' else oauth.exchange_refresh_token
    original = oauth._issue_token_pair

    class FailAccessInsert:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, query, params=None):
            if 'INSERT INTO oauth_access_tokens' in query:
                raise RuntimeError('injected access insert failure')
            return self.conn.execute(query, params)

    def fail(conn, *args, **kwargs):
        return original(FailAccessInsert(conn), *args, **kwargs)

    with connect() as conn:
        before = conn.execute('SELECT count(*) AS n FROM oauth_refresh_tokens WHERE client_id=%s',
                              (grant['client_id'],)).fetchone()['n']
    with monkeypatch.context() as patch:
        patch.setattr(oauth, '_issue_token_pair', fail)
        with pytest.raises(RuntimeError, match='injected access insert failure'):
            exchange(form)
    with connect() as conn:
        assert conn.execute('SELECT count(*) AS n FROM oauth_refresh_tokens WHERE client_id=%s',
                            (grant['client_id'],)).fetchone()['n'] == before
        if kind == 'code':
            row = conn.execute('SELECT consumed_at FROM oauth_authorization_codes WHERE code_hash=%s',
                                (sha256(form['code']),)).fetchone()
            assert row['consumed_at'] is None
        else:
            row = conn.execute('SELECT rotated_at FROM oauth_refresh_tokens WHERE token_hash=%s',
                                (sha256(form['refresh_token']),)).fetchone()
            assert row['rotated_at'] is None
    assert exchange(form).status_code == 200


@pytest.mark.parametrize('action', ['reuse', 'consent', 'token'])
def test_concurrent_rotation_and_revocation_leave_no_live_descendants(grant, monkeypatch, action):
    pair = tokens(grant)
    form = refresh_form(grant, pair)
    consent = consent_id(grant)
    entered, release, attempted = Event(), Event(), Event()
    original = oauth._issue_token_pair
    original_lock = oauth._grant_lock

    def pause(conn, *args, **kwargs):
        entered.set()
        assert release.wait(10), 'test did not release token issuance'
        return original(conn, *args, **kwargs)

    def revoke():
        if action == 'reuse':
            return oauth.exchange_refresh_token(form)
        if action == 'consent':
            return oauth.revoke_consent(consent)
        return oauth.revoke_token({'token': pair['refresh_token'], 'client_id': grant['client_id']})

    def observe_lock(conn, row):
        if entered.is_set():
            attempted.set()
        return original_lock(conn, row)

    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=2) as pool:
        patch.setattr(oauth, '_issue_token_pair', pause)
        patch.setattr(oauth, '_grant_lock', observe_lock)
        first = pool.submit(oauth.exchange_refresh_token, form)
        try:
            assert entered.wait(10)
            second = pool.submit(revoke)
            assert attempted.wait(10)
            assert not second.done(), 'revocation bypassed the in-flight issuance transaction'
        finally:
            release.set()
        result = first.result(timeout=15)
        second.result(timeout=15)
    assert result.status_code == 200
    child = json.loads(result.body)
    assert oauth.oauth_access_token_principal(child['access_token']) is None
    assert oauth.exchange_refresh_token(refresh_form(grant, child)).status_code == 400
    with connect() as conn:
        assert conn.execute('''SELECT count(*) AS n FROM oauth_refresh_tokens
            WHERE client_id=%s AND revoked_at IS NULL''', (grant['client_id'],)).fetchone()['n'] == 0


def test_concurrent_code_exchange_and_consent_revocation(grant, monkeypatch):
    form = code_form(grant)
    consent = consent_id(grant)
    entered, release, attempted = Event(), Event(), Event()
    original = oauth._issue_token_pair
    original_lock = oauth._grant_lock

    def pause(conn, *args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(conn, *args, **kwargs)

    def observe_lock(conn, row):
        if entered.is_set():
            attempted.set()
        return original_lock(conn, row)

    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=2) as pool:
        patch.setattr(oauth, '_issue_token_pair', pause)
        patch.setattr(oauth, '_grant_lock', observe_lock)
        issuing = pool.submit(oauth.exchange_authorization_code, form)
        try:
            assert entered.wait(10)
            revoking = pool.submit(oauth.revoke_consent, consent)
            assert attempted.wait(10)
            assert not revoking.done()
        finally:
            release.set()
        response = issuing.result(timeout=15)
        revoking.result(timeout=15)
    assert response.status_code == 200
    assert oauth.oauth_access_token_principal(json.loads(response.body)['access_token']) is None
    assert oauth.exchange_authorization_code(form).status_code == 400


@pytest.mark.parametrize('metadata', [None, [], 'client', {},
    {'redirect_uris': 'https://example.com/cb'}, {'redirect_uris': [123]},
    {'redirect_uris': ['https://example.com/cb'] * 11},
    {'redirect_uris': ['https://example.com/' + 'x' * 4000]},
    *[{'redirect_uris': ['https://example.com/cb'], **extra} for extra in [
        {'client_name': 123}, {'client_name': 'x' * 301}, {'client_name': ' '},
        {'application_type': []}, {'token_endpoint_auth_method': []},
        {'grant_types': 'authorization_code'}, {'grant_types': [123]},
        {'response_types': 'code'}, {'response_types': ['code', 'token']},
    ]],
])
def test_registration_rejects_invalid_metadata_before_database(metadata, monkeypatch):
    def no_database():
        pytest.fail('invalid registration reached database')
    monkeypatch.setattr(oauth, 'connect', no_database)
    with pytest.raises(HTTPException) as error:
        oauth.dynamic_register(metadata)
    assert error.value.status_code == 400


@pytest.fixture
def registered():
    ids = []
    try:
        yield ids
    finally:
        with connect() as conn:
            conn.execute('DELETE FROM oauth_clients WHERE client_id=ANY(%s::text[])', (ids,))
            conn.commit()


def test_registration_discards_unknown_fields_and_preserves_supported_client(registered):
    result = oauth.dynamic_register({'redirect_uris': ['http://localhost/callback'],
        'client_name': 'MCP desktop', 'grant_types': ['authorization_code', 'refresh_token'],
        'unknown': {'untrusted_blob': 'x' * 100000}})
    registered.append(result['client_id'])
    assert result['grant_types'] == ['authorization_code', 'refresh_token']
    with connect() as conn:
        stored = conn.execute('SELECT metadata FROM oauth_clients WHERE client_id=%s',
                               (result['client_id'],)).fetchone()['metadata']
    assert 'unknown' not in stored and len(json.dumps(stored)) < 1000
    assert oauth._load_client(result['client_id'], 'http://localhost:54231/callback')['is_active']


def test_registration_quota_is_atomic_for_concurrent_requests(registered, monkeypatch):
    with connect() as conn:
        existing = conn.execute("SELECT count(*) AS n FROM oauth_clients WHERE registration_type='dynamic'").fetchone()['n']
    monkeypatch.setattr(oauth, 'DYNAMIC_CLIENT_LIMIT', existing + 1)
    barrier = Barrier(2, timeout=10)

    def register():
        barrier.wait()
        try:
            result = oauth.dynamic_register({'redirect_uris': ['https://example.com/callback']})
            return result['client_id']
        except HTTPException as error:
            assert error.status_code == 429
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(register) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]
    registered.extend(result for result in results if result)
    assert len(registered) == 1
    with connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM oauth_clients WHERE registration_type='dynamic'").fetchone()['n'] == existing + 1


def test_registration_cleanup_keeps_clients_with_pending_or_active_grants(grant, registered):
    pair = tokens(grant)
    pending = code_form(grant)
    with connect() as conn:
        conn.execute("UPDATE oauth_clients SET registration_type='dynamic',created_at=now()-interval '40 days',last_used_at=NULL WHERE client_id=%s", (grant['client_id'],))
        conn.commit()
    unused = oauth.dynamic_register({'redirect_uris': ['https://example.com/unused']})['client_id']
    registered.append(unused)
    with connect() as conn:
        conn.execute("UPDATE oauth_clients SET created_at=now()-interval '40 days',last_used_at=NULL WHERE client_id=%s", (unused,))
        conn.commit()
    replacement = oauth.dynamic_register({'redirect_uris': ['https://example.com/new']})['client_id']
    registered.append(replacement)
    with connect() as conn:
        assert conn.execute('SELECT 1 FROM oauth_clients WHERE client_id=%s', (unused,)).fetchone() is None
        assert conn.execute('SELECT 1 FROM oauth_clients WHERE client_id=%s', (grant['client_id'],)).fetchone()
    assert oauth.oauth_access_token_principal(pair['access_token'])
    assert oauth.exchange_authorization_code(pending).status_code == 200
