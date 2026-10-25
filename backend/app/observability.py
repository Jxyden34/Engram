"""Bounded project aggregates without content, request identifiers or arbitrary labels."""

from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache, wraps
from math import ceil, isfinite
from time import perf_counter, time

import httpx
from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from rq import Queue
from rq.registry import FailedJobRegistry, StartedJobRegistry

from app.config import settings
from app.database import connect, current_project_id

OPERATIONS = ('api', 'embedding', 'ollama')
BUCKET_SECONDS = 300
BUCKET_COUNT = 288
BOUNDS_MS = (10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 90000, 300000)


@lru_cache(maxsize=1)
def redis_client():
    return Redis.from_url(settings().redis_url, decode_responses=True,
                          socket_connect_timeout=.2, socket_timeout=.3,
                          retry=Retry(NoBackoff(), 0))


def _key(operation, bucket):
    return f'engram:observability:v1:{current_project_id()}:{operation}:{bucket}'


def observe(operation, seconds, failed=False):
    """Telemetry failures must not alter application behavior; labels are a fixed allowlist."""
    if operation not in OPERATIONS or not isfinite(seconds) or seconds < 0:
        return
    milliseconds = seconds * 1000
    key = _key(operation, int(time() // BUCKET_SECONDS))
    try:
        with redis_client().pipeline(transaction=True) as pipe:
            pipe.hincrby(key, 'count', 1)
            pipe.hincrbyfloat(key, 'total_ms', milliseconds)
            pipe.hincrby(key, 'errors', int(bool(failed)))
            pipe.hincrby(key, f'bin:{bisect_left(BOUNDS_MS, milliseconds)}', 1)
            pipe.expire(key, BUCKET_SECONDS * (BUCKET_COUNT + 1))
            pipe.execute()
    except Exception:
        pass


def timed(operation):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            start, failed = perf_counter(), True
            try:
                result = fn(*args, **kwargs)
                failed = False
                return result
            finally:
                observe(operation, perf_counter() - start, failed)
        return wrapped
    return decorate


def _rollup(rows):
    count = sum(int(row.get('count', 0)) for row in rows)
    errors = sum(int(row.get('errors', 0)) for row in rows)
    total = sum(float(row.get('total_ms', 0)) for row in rows)
    bins = [sum(int(row.get(f'bin:{i}', 0)) for row in rows) for i in range(len(BOUNDS_MS) + 1)]
    cumulative, p95, overflow = 0, None, False
    for i, n in enumerate(bins):
        cumulative += n
        if count and cumulative >= ceil(count * .95):
            p95 = BOUNDS_MS[i] if i < len(BOUNDS_MS) else None
            overflow = i == len(BOUNDS_MS)
            break
    return {'count':count, 'errors':errors, 'error_rate':errors/count if count else None,
            'mean_ms':round(total/count, 2) if count else None,
            'p95_upper_ms':p95, 'p95_overflow':overflow}


def latency_snapshot():
    end = int(time() // BUCKET_SECONDS)
    try:
        with redis_client().pipeline(transaction=False) as pipe:
            for operation in OPERATIONS:
                for bucket in range(end-BUCKET_COUNT+1, end+1):
                    pipe.hgetall(_key(operation, bucket))
            rows = pipe.execute()
        return {'status':'ok', 'window_started_at':datetime.fromtimestamp((end-BUCKET_COUNT+1)*BUCKET_SECONDS, timezone.utc).isoformat(),
                'operations':{op:_rollup(rows[i*BUCKET_COUNT:(i+1)*BUCKET_COUNT]) for i,op in enumerate(OPERATIONS)}}
    except Exception:
        return {'status':'unavailable', 'operations':{}}


def project_snapshot():
    try:
        with connect(timeout=2) as conn:
            conn.execute("SET LOCAL statement_timeout='1500ms'")
            documents = dict(conn.execute("""SELECT count(*) FILTER(WHERE status='queued') AS queued,
                count(*) FILTER(WHERE status='processing') AS processing,
                count(*) FILTER(WHERE status='failed') AS failed,
                count(*) FILTER(WHERE status='ready' AND processed_at>now()-interval '24 hours') AS ready_24h
                FROM documents WHERE deleted_at IS NULL""").fetchone())
            candidates = dict(conn.execute("""WITH candidates AS (
                SELECT status,reviewed_at FROM candidate_memories UNION ALL
                SELECT status,reviewed_at FROM document_candidate_memories)
                SELECT count(*) FILTER(WHERE status='pending') AS pending,
                count(*) FILTER(WHERE status='accepted' AND reviewed_at>now()-interval '24 hours') AS accepted_24h,
                count(*) FILTER(WHERE status='rejected' AND reviewed_at>now()-interval '24 hours') AS rejected_24h
                FROM candidates""").fetchone())
            connectors = dict(conn.execute("""SELECT count(*) AS total,
                count(*) FILTER(WHERE enabled) AS enabled,
                count(*) FILTER(WHERE enabled AND last_status='failed') AS failing,
                count(*) FILTER(WHERE enabled AND next_sync_at<now()-interval '5 minutes') AS overdue,
                max(last_sync_at) AS last_sync_at FROM connectors""").fetchone())
            runs = dict(conn.execute("""SELECT count(*) FILTER(WHERE status='ready') AS ready,
                count(*) FILTER(WHERE status='failed') AS failed,
                COALESCE(sum(items_changed),0)::bigint AS items_changed FROM connector_sync_runs
                WHERE created_at>now()-interval '24 hours'""").fetchone())
        reviewed = candidates['accepted_24h'] + candidates['rejected_24h']
        candidates['acceptance_rate_24h'] = candidates['accepted_24h']/reviewed if reviewed else None
        documents['ready_per_hour_24h'] = round(documents['ready_24h']/24, 2)
        return {'status':'ok', 'documents':documents, 'candidates':candidates,
                'connectors':connectors, 'connector_runs_24h':runs}
    except Exception:
        return {'status':'unavailable'}


def queue_snapshot():
    try:
        client = redis_client()
        queue = Queue('document-ingest', connection=client)
        with client.pipeline(transaction=False) as pipe:
            pipe.llen(queue.key)
            pipe.zcard(StartedJobRegistry(queue=queue).key)
            pipe.zcard(FailedJobRegistry(queue=queue).key)
            queued, started, failed = pipe.execute()
        return {'status':'ok', 'scope':'deployment', 'name':'document-ingest',
                'queued':queued, 'started_registry':started, 'failed_registry':failed}
    except Exception:
        return {'status':'unavailable', 'scope':'deployment'}


def _probe(url):
    start = perf_counter()
    try:
        response = httpx.get(url, timeout=httpx.Timeout(1.5), follow_redirects=False)
        return {'status':'ok' if response.status_code == 200 else 'unavailable',
                'latency_ms':round((perf_counter()-start)*1000, 2)}
    except Exception:
        return {'status':'unavailable', 'latency_ms':None}


def snapshot():
    cfg = settings()
    with ThreadPoolExecutor(max_workers=2) as pool:
        minio = pool.submit(_probe, f"{'https' if cfg.minio_secure else 'http'}://{cfg.minio_endpoint}/minio/health/ready")
        ollama = pool.submit(_probe, cfg.ollama_url.rstrip('/')+'/api/tags')
        project, latency, queue = project_snapshot(), latency_snapshot(), queue_snapshot()
        services = {'postgresql':{'status':project['status']}, 'redis':{'status':queue['status']},
                    'object_storage':minio.result(), 'ollama':ollama.result()}
    return {'project_id':current_project_id(), 'generated_at':datetime.now(timezone.utc).isoformat(),
            'latency':latency, 'project':project, 'queue':queue, 'services':services}
