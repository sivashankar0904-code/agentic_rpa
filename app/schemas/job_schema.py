from typing import Any

from pydantic import BaseModel


class JobEnqueueRead(BaseModel):
    task_id: str


class JobStatusRead(BaseModel):
    task_id: str
    status: str
    result: Any | None = None
