from app.celery_app import celery_app
from app.core.response import ServiceResponse, ServiceStatus
from app.schemas.job_schema import JobEnqueueRead, JobStatusRead

# Enqueue by task name via celery_app.send_task(), not by importing the task
# functions themselves: rpa_tasks.py and training_tasks.py pull in nodriver
# and torch respectively (see their module docstrings), and this service
# layer is imported by the api process, which carries neither dependency —
# only the worker that actually runs a task needs to import its module.


def enqueue_gst_login() -> ServiceResponse[JobEnqueueRead]:
    result = celery_app.send_task("agentic_rpa.gst_login")
    return ServiceResponse(status=ServiceStatus.SUCCESS, data=JobEnqueueRead(task_id=result.id))


def enqueue_train_captcha_model() -> ServiceResponse[JobEnqueueRead]:
    result = celery_app.send_task("agentic_rpa.train_captcha_model")
    return ServiceResponse(status=ServiceStatus.SUCCESS, data=JobEnqueueRead(task_id=result.id))


def get_job_status(task_id: str) -> ServiceResponse[JobStatusRead]:
    # AsyncResult is looked up purely by task_id against the shared Celery
    # backend, independent of which task class produced it — celery_app is
    # used here (rather than any one task's bound .AsyncResult) so this
    # works for gst_login, train_captcha_model, or any future task alike.
    result = celery_app.AsyncResult(task_id)

    # On failure, Celery's .result is the raised Exception object itself,
    # which FastAPI/Pydantic can't serialize (500s the whole response) — stringify it.
    task_result = result.result
    if result.ready() and isinstance(task_result, BaseException):
        task_result = str(task_result)

    job_status = JobStatusRead(
        task_id=task_id,
        status=result.status,
        result=task_result if result.ready() else None,
    )
    return ServiceResponse(status=ServiceStatus.SUCCESS, data=job_status)
