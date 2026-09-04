from app.core.response import ServiceResponse, ServiceStatus
from app.schemas.job_schema import JobEnqueueRead, JobStatusRead
from app.tasks import gst_login


def enqueue_gst_login() -> ServiceResponse[JobEnqueueRead]:
    result = gst_login.delay()
    return ServiceResponse(status=ServiceStatus.SUCCESS, data=JobEnqueueRead(task_id=result.id))


def get_job_status(task_id: str) -> ServiceResponse[JobStatusRead]:
    result = gst_login.AsyncResult(task_id)

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
