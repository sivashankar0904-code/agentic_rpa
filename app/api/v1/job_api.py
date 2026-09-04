from fastapi import APIRouter

from app.core.error.error import raise_for_status
from app.core.jobs import jobs as jobs_service
from app.schemas.job_schema import JobEnqueueRead, JobStatusRead

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post(
    "/gst-login",
    response_model=JobEnqueueRead,
    operation_id="enqueueGstLogin",
    summary="Enqueue a GST portal login job",
)
def enqueue_gst_login() -> JobEnqueueRead:
    """Enqueue a GST portal login job on a Celery worker and return its task id."""
    response = jobs_service.enqueue_gst_login()
    raise_for_status(response.status)
    return response.data


@router.get(
    "/{task_id}",
    response_model=JobStatusRead,
    operation_id="getJobStatus",
    summary="Get job status",
)
def get_job_status(task_id: str) -> JobStatusRead:
    response = jobs_service.get_job_status(task_id)
    raise_for_status(response.status)
    return response.data
