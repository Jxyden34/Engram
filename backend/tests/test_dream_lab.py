from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import dream_lab as dreams
from app.database import connect, project_scope

CONTENT = ['The tablet needs a simple offline checklist for checking server health.',
           'A small server costs 20 pounds per month and has a limited memory budget.']


def artifact():
    return {'title': 'Offline lab planner', 'premise': 'Combine the tablet checklist with an illustrative cost planner.',
            'inspiration': [{'source': i+1, 'quote': text[:30]} for i, text in enumerate(CONTENT)],
            'widgets': [{'id': 'servers', 'kind': 'number', 'title': 'Server count', 'value': 2, 'maximum': 10},
                        {'id': 'cost', 'kind': 'metric', 'title': 'Illustrative monthly cost',
                         'terms': [{'input_id': 'servers', 'coefficient': 20}], 'unit': 'GBP'},
                        {'id': 'steps', 'kind': 'checklist', 'title': 'Check the lab', 'items': ['Check health', 'Record result']},
                        {'id': 'board', 'kind': 'board', 'title': 'References', 'items': ['Server budget', 'Tablet checklist']}],
            'how_to_test': ['Change the server count and check the monthly cost.'],
            'limitations': 'Illustrative numbers; no connection to real services.'}


def test_dreams_only_accept_bounded_connected_data():
    parsed = dreams.Artifact.model_validate(artifact())
    assert dreams.baseline(parsed.widgets[1], {'servers': 3}) == 60
    for mutate in [lambda a: a.update(html='<script>bad()</script>'),
                   lambda a: a['widgets'][1]['terms'][0].update(input_id='missing'),
                   lambda a: a['widgets'][0].update(value=float('nan')),
                   lambda a: a['widgets'][0].update(value=20),
                   lambda a: a['inspiration'][1].update(source=1),
                   lambda a: a['widgets'][1].update(divide_by=0),
                   lambda a: a['widgets'][1].update(id='servers')]:
        data = artifact(); mutate(data)
        with pytest.raises(ValidationError): dreams.Artifact.model_validate(data)


def test_dream_schedule_always_uses_next_future_utc_hour():
    before = datetime.now(timezone.utc)
    for hour in range(24):
        date = dreams.next_night(hour)
        assert date > before and date.hour == hour and date.minute == 0
        assert (date-before).total_seconds() <= 86401


def test_small_model_gets_one_bounded_repair_attempt(monkeypatch):
    import json
    requests = []
    def model(system, user, **kwargs):
        requests.append((json.loads(user), kwargs))
        data = artifact()
        if len(requests) == 1: data['widgets'][0]['value'] = 11
        return data
    monkeypatch.setattr(dreams, '_ollama_json', model)
    sources = [{'content': c} for c in CONTENT]
    result = dreams.generate(sources, 'Invent something')
    assert result.widgets[0].value == 2 and len(requests) == 2
    assert requests[1][0]['repair_errors']
    assert all(r[1]['timeout'] == 90.0 for r in requests)


@pytest.fixture
def corpus():
    with connect() as conn:
        projects = [str(conn.execute("INSERT INTO projects(slug,name) VALUES(%s,'Dream test') RETURNING id",
                    ('dream-'+uuid4().hex,)).fetchone()['id']) for _ in range(2)]; conn.commit()
    ids = []
    with project_scope(projects[0]), connect() as conn:
        for text in CONTENT:
            ids.append(str(conn.execute("""INSERT INTO memories(title,content,created_by,updated_by)
                VALUES('Dream inspiration',%s,'test','test') RETURNING id""", (text,)).fetchone()['id']))
        conn.commit()
    try:
        yield projects, ids
    finally:
        for project in projects:
            with project_scope(project), connect() as conn:
                conn.execute('DELETE FROM dream_runs'); conn.execute('DELETE FROM dream_schedules')
                conn.execute('DELETE FROM memories'); conn.commit()
        with connect() as conn:
            conn.execute('DELETE FROM projects WHERE id=ANY(%s::uuid[])', (projects,)); conn.commit()


def model_for_sources(system, user, **kwargs):
    data = artifact(); context = __import__('json').loads(user)
    data['inspiration'] = [{'source': i+1, 'quote': s['content'][:30]} for i, s in enumerate(context['sources'])]
    return data


def test_dream_lifecycle_isolation_evolution_and_stale_sources(corpus, monkeypatch):
    from app import connectors, licensing
    queued = []
    monkeypatch.setattr(connectors, 'queue', lambda: SimpleNamespace(enqueue=lambda *a, **k: queued.append((a, k))))
    monkeypatch.setattr(licensing, 'require_commercial_license', lambda: None)
    monkeypatch.setattr(dreams, '_ollama_json', model_for_sources)
    monkeypatch.setattr(dreams, 'signed_in', lambda *a: SimpleNamespace(actor='test'))
    projects, memories = corpus
    with project_scope(projects[0]):
        identifier = str(dreams.queue_dream(dreams.DreamRequest(), 'test')['id'])
        assert queued[0][1]['meta']['project_id'] == projects[0]
        with pytest.raises(HTTPException) as busy: dreams.queue_dream(dreams.DreamRequest(), 'test')
        assert busy.value.status_code == 409
        # Call the worker inside its project, bypassing RQ's job metadata wrapper.
        dreams.run_dream.__wrapped__(identifier)
        result = dreams.get_dream(identifier)
        assert result['status'] == 'ready' and not result['needs_review']
        assert result['artifact']['widgets'][1]['kind'] == 'metric'
        assert any('Baseline calculation' in r for r in result['report'])
        assert dreams.keep_route(UUID(identifier), None)['status'] == 'kept'
        child = str(dreams.queue_dream(dreams.DreamRequest(parent_id=identifier, direction='Make it simpler'), 'test')['id'])
        dreams.run_dream.__wrapped__(child)
        assert dreams.get_dream(child)['parent_id'] == result['id']
    with project_scope(projects[1]):
        with pytest.raises(HTTPException) as absent: dreams.get_dream(identifier)
        assert absent.value.status_code == 404
        with pytest.raises(HTTPException): dreams.queue_dream(dreams.DreamRequest(parent_id=identifier), 'test')
    with project_scope(projects[0]), connect() as conn:
        conn.execute('UPDATE memories SET content=%s WHERE id=%s', ('Changed source content', memories[0])); conn.commit()
        stale = dreams.get_dream(identifier)
        assert stale['needs_review'] and stale['artifact'] is None and stale['sources'] == []
        with pytest.raises(HTTPException): dreams.keep_route(UUID(identifier), None)
        with pytest.raises(HTTPException): dreams.queue_dream(dreams.DreamRequest(parent_id=identifier), 'test')
        assert conn.execute('SELECT count(*) AS n FROM memories').fetchone()['n'] == 2
        assert dreams.destroy_route(UUID(child), None)['status'] == 'destroyed'


def test_unverified_model_output_fails_without_leaking_and_destroyed_jobs_stay_gone(corpus, monkeypatch):
    from app import connectors, licensing
    monkeypatch.setattr(connectors, 'queue', lambda: SimpleNamespace(enqueue=lambda *a, **k: None))
    monkeypatch.setattr(licensing, 'require_commercial_license', lambda: None)
    def invalid(*a, **k):
        data = artifact(); data['inspiration'][0]['quote'] = 'This quotation is fabricated'
        return data
    monkeypatch.setattr(dreams, '_ollama_json', invalid)
    with project_scope(corpus[0][0]):
        identifier = str(dreams.queue_dream(dreams.DreamRequest(), 'test')['id'])
        dreams.run_dream.__wrapped__(identifier)
        result = dreams.get_dream(identifier)
        assert result['status'] == 'failed' and result['artifact'] is None
        assert 'fabricated' not in result['error_message']
        second = str(dreams.queue_dream(dreams.DreamRequest(), 'test')['id'])
        with connect() as conn:
            conn.execute('DELETE FROM dream_runs WHERE id=%s', (second,)); conn.commit()
        dreams.run_dream.__wrapped__(second)
        with pytest.raises(HTTPException): dreams.get_dream(second)


def test_nightly_schedule_queues_once_and_queue_failure_is_visible(corpus, monkeypatch):
    from app import connectors
    queued = []
    monkeypatch.setattr(connectors, 'queue', lambda: SimpleNamespace(enqueue=lambda *a, **k: queued.append(a)))
    project = corpus[0][0]
    with project_scope(project), connect() as conn:
        conn.execute("""INSERT INTO dream_schedules(enabled,hour_utc,next_run_at,created_by)
            VALUES(true,2,now()-interval '1 hour','test')"""); conn.commit()
    dreams.queue_due_dreams(); dreams.queue_due_dreams()
    assert len(queued) == 1
    with project_scope(project), connect() as conn:
        conn.execute('DELETE FROM dream_runs'); conn.commit()
        def fail(*a, **k): raise RuntimeError('private-provider-detail')
        monkeypatch.setattr(connectors, 'queue', lambda: SimpleNamespace(enqueue=fail))
        with pytest.raises(HTTPException) as error: dreams.queue_dream(dreams.DreamRequest(), 'test')
        assert error.value.status_code == 503 and 'private' not in error.value.detail
        assert conn.execute("SELECT status FROM dream_runs").fetchone()['status'] == 'failed'
