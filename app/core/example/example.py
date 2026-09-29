import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import ServiceResponse, ServiceStatus
from app.models import example_model
from app.models.example_model import Example
from app.schemas.example_schema import ExampleCreate, ExamplePatch, ExampleUpdate


def _search_tags(obj: Example) -> list[str]:
    tags = [str(obj.id)]
    if obj.name:
        tags.append(obj.name)
    return tags


async def create_example(db: AsyncSession, payload: ExampleCreate) -> ServiceResponse[Example]:
    now = datetime.now(UTC)
    obj = Example(
        organisation_id=payload.organisation_id,
        name=payload.name,
        meta=payload.meta,
        status=payload.status,
        created_at=now,
        updated_at=now,
    )
    obj = await example_model.create_example(db, obj)
    obj.search_tags = _search_tags(obj)
    await db.commit()
    await db.refresh(obj)
    return ServiceResponse(status=ServiceStatus.SUCCESS, data=obj)


async def get_example(db: AsyncSession, example_id: uuid.UUID) -> ServiceResponse[Example]:
    obj = await example_model.get_example(db, example_id)
    if obj is None:
        return ServiceResponse(status=ServiceStatus.NOT_FOUND)
    return ServiceResponse(status=ServiceStatus.SUCCESS, data=obj)


async def list_examples(
    db: AsyncSession,
    *,
    organisation_id: uuid.UUID,
    is_active: bool | None,
    sort_by: str,
    sort_order: str,
    limit: int | None,
    offset: int,
) -> ServiceResponse[list[Example]]:
    if limit is None:
        objs = await example_model.list_examples(
            db,
            organisation_id=organisation_id,
            is_active=is_active,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    else:
        objs = await example_model.list_examples_pagination(
            db,
            organisation_id=organisation_id,
            is_active=is_active,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )
    return ServiceResponse(status=ServiceStatus.SUCCESS, data=objs)


async def patch_example(
    db: AsyncSession, example_id: uuid.UUID, organisation_id: uuid.UUID, payload: ExamplePatch
) -> ServiceResponse[Example]:
    existing = await example_model.get_example_by_organisation(db, example_id, organisation_id)
    if existing is None:
        return ServiceResponse(status=ServiceStatus.NOT_FOUND)

    fields = payload.model_dump(exclude_unset=True)
    fields["updated_at"] = datetime.now(UTC)
    obj = await example_model.patch_example(db, example_id, **fields)
    obj.search_tags = _search_tags(obj)
    await db.commit()
    await db.refresh(obj)
    return ServiceResponse(status=ServiceStatus.SUCCESS, data=obj)


async def update_example(
    db: AsyncSession, example_id: uuid.UUID, organisation_id: uuid.UUID, payload: ExampleUpdate
) -> ServiceResponse[Example]:
    existing = await example_model.get_example_by_organisation(db, example_id, organisation_id)
    if existing is None:
        return ServiceResponse(status=ServiceStatus.NOT_FOUND)

    replacement = Example(
        name=payload.name,
        meta=payload.meta,
        is_active=payload.is_active,
        status=payload.status,
        updated_at=datetime.now(UTC),
    )
    obj = await example_model.update_example(db, example_id, replacement)
    obj.search_tags = _search_tags(obj)
    await db.commit()
    await db.refresh(obj)
    return ServiceResponse(status=ServiceStatus.SUCCESS, data=obj)


async def delete_example(
    db: AsyncSession, example_id: uuid.UUID, organisation_id: uuid.UUID
) -> ServiceResponse[None]:
    existing = await example_model.get_example_by_organisation(db, example_id, organisation_id)
    if existing is None:
        return ServiceResponse(status=ServiceStatus.NOT_FOUND)

    await example_model.delete_example(db, example_id)
    await db.commit()
    return ServiceResponse(status=ServiceStatus.SUCCESS)
