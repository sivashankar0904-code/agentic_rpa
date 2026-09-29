import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExampleCreate(BaseModel):
    organisation_id: uuid.UUID
    name: str
    meta: dict = {}
    status: dict | None = None


class ExampleUpdate(BaseModel):
    name: str
    meta: dict = {}
    is_active: bool = True
    status: dict | None = None


class ExamplePatch(BaseModel):
    name: str | None = None
    meta: dict | None = None
    is_active: bool | None = None
    status: dict | None = None


class ExampleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    meta: dict
    is_active: bool
    status: dict | None
    search_tags: list[str] | None
    created_at: datetime
    updated_at: datetime
