from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CaptchaLabelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # built via model_validate() from the ORM row

    object_name: str
    label: str | None
    is_solved: bool
    created_at: datetime
    updated_at: datetime | None


class CaptchaLabelSolveRequest(BaseModel):
    label: str


class CaptchaPredictionRead(BaseModel):
    object_name: str
    predicted_label: str
