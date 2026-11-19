from uuid import uuid4

from redis import Redis
from rq import Queue, Worker, get_current_job
from rq.job import JobStatus

from app.config import settings
from app.database import DEFAULT_PROJECT_ID, current_project_id, project_job, project_scope


@project_job
def read_worker_project(fail=False):
    if fail:
        raise ValueError("Expected worker regression failure")
    return {"project_id": current_project_id(), "job_id": get_current_job().id}


def test_worker_preserves_project_metadata_results_and_failure_registry():
    """Exercise the production fork worker and serialized jobs against real Redis."""
    client = Redis.from_url(settings().redis_url)
    queue = Queue("rq-regression-" + uuid4().hex, connection=client)
    project_id, parent_id = str(uuid4()), str(uuid4())
    jobs = []
    try:
        jobs.append(queue.enqueue(read_worker_project, meta={"project_id": project_id}))
        jobs.append(queue.enqueue(read_worker_project))
        jobs.append(queue.enqueue(read_worker_project, fail=True, meta={"project_id": project_id}))
        with project_scope(parent_id):
            worker = Worker([queue], connection=client)
            assert worker.work(burst=True)
            assert current_project_id() == parent_id
        for job, expected_project in zip(jobs[:2], [project_id, DEFAULT_PROJECT_ID]):
            assert job.get_status(refresh=True) == JobStatus.FINISHED
            assert job.return_value(refresh=True) == {"project_id": expected_project, "job_id": job.id}
        assert jobs[2].get_status(refresh=True) == JobStatus.FAILED
        assert queue.failed_job_registry.get_job_ids() == [jobs[2].id]
        assert queue.started_job_registry.count == 0
        assert queue.count == 0
    finally:
        for job in jobs:
            job.delete()
        queue.delete()
        client.close()
