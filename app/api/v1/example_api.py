import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error.error import raise_for_status
from app.core.example import example as example_service
from app.db.session import get_db
from app.models.example_model import Example
from app.schemas.example_schema import ExampleCreate, ExamplePatch, ExampleUpdate

router = APIRouter(prefix="/examples", tags=["example"])


@router.post("", response_model=Example, status_code=201, operation_id="createExample", summary="Create an example")
async def create_example(payload: ExampleCreate, db: AsyncSession = Depends(get_db)) -> Example:
    response = await example_service.create_example(db, payload)
    raise_for_status(response.status)
    return response.data


@router.get("/{id}", response_model=Example, operation_id="getExample", summary="Get an example by id")
async def get_example(id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Example:
    response = await example_service.get_example(db, id)
    raise_for_status(response.status)
    return response.data


@router.get("", response_model=list[Example], operation_id="listExamples", summary="List examples")
async def list_examples(
    organisation_id: uuid.UUID,
    is_active: bool | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int | None = None,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[Example]:
    response = await example_service.list_examples(
        db,
        organisation_id=organisation_id,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    raise_for_status(response.status)
    return response.data


@router.patch("/{id}", response_model=Example, operation_id="patchExample", summary="Partially update an example")
async def patch_example(
    id: uuid.UUID, organisation_id: uuid.UUID, payload: ExamplePatch, db: AsyncSession = Depends(get_db)
) -> Example:
    response = await example_service.patch_example(db, id, organisation_id, payload)
    raise_for_status(response.status)
    return response.data


@router.put("/{id}", response_model=Example, operation_id="updateExample", summary="Replace an example")
async def update_example(
    id: uuid.UUID, organisation_id: uuid.UUID, payload: ExampleUpdate, db: AsyncSession = Depends(get_db)
) -> Example:
    response = await example_service.update_example(db, id, organisation_id, payload)
    raise_for_status(response.status)
    return response.data


@router.delete("/{id}", status_code=204, operation_id="deleteExample", summary="Soft-delete an example")
async def delete_example(id: uuid.UUID, organisation_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    response = await example_service.delete_example(db, id, organisation_id)
    raise_for_status(response.status)
    return response.data
