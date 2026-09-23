import psycopg
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from psycopg.rows import dict_row
from app.config import settings

DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000001"
_project_id: ContextVar[str] = ContextVar("memorybank_project_id", default=DEFAULT_PROJECT_ID)


def current_project_id() -> str:
    return _project_id.get()


@contextmanager
def project_scope(project_id: str):
    token = _project_id.set(project_id)
    try:
        yield
    finally:
        _project_id.reset(token)


def project_job(fn):
    """Restore the project attached to an RQ job before opening data connections."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        from rq import get_current_job
        job = get_current_job()
        project_id = job.meta.get("project_id", DEFAULT_PROJECT_ID) if job else DEFAULT_PROJECT_ID
        with project_scope(project_id):
            return fn(*args, **kwargs)
    return wrapped


def connect():
    conn = psycopg.connect(settings().database_url, row_factory=dict_row)
    conn.execute("SET ROLE memorybank_runtime")
    conn.execute("SELECT set_config('memorybank.project_id', %s, false)", (current_project_id(),))
    return conn
