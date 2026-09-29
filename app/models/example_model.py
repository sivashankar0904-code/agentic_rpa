import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Text, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_SORTABLE_FIELDS = {
    "created_at": "created_at",
    "updated_at": "updated_at",
    "name": "name",
}


class Example(Base):
    __tablename__ = "example"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    search_tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


async def create_example(db: AsyncSession, obj: Example) -> Example:
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


async def get_example(db: AsyncSession, example_id: uuid.UUID) -> Example | None:
    return await db.get(Example, example_id)


async def get_example_by_organisation(
    db: AsyncSession, example_id: uuid.UUID, organisation_id: uuid.UUID
) -> Example | None:
    result = await db.execute(
        select(Example).where(
            Example.id == example_id, Example.organisation_id == organisation_id
        )
    )
    return result.scalars().first()


async def list_examples(
    db: AsyncSession,
    *,
    organisation_id: uuid.UUID,
    is_active: bool | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    paginate: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[Example]:
    stmt = select(Example).where(Example.organisation_id == organisation_id)
    if is_active is not None:
        stmt = stmt.where(Example.is_active == is_active)

    column_name = _SORTABLE_FIELDS.get(sort_by, "created_at")
    column = getattr(Example, column_name)
    stmt = stmt.order_by(column.desc() if sort_order == "desc" else column.asc())

    if paginate:
        stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_examples_pagination(
    db: AsyncSession,
    *,
    organisation_id: uuid.UUID,
    is_active: bool | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 20,
    offset: int = 0,
) -> list[Example]:
    return await list_examples(
        db,
        organisation_id=organisation_id,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
        paginate=True,
        limit=limit,
        offset=offset,
    )


async def patch_example(db: AsyncSession, example_id: uuid.UUID, **fields) -> Example | None:
    obj = await db.get(Example, example_id)
    if obj is None:
        return None
    if "meta" in fields and fields["meta"] is not None:
        obj.meta = {**obj.meta, **fields.pop("meta")}
    for key, value in fields.items():
        if value is not None:
            setattr(obj, key, value)
    await db.flush()
    await db.refresh(obj)
    return obj


async def update_example(db: AsyncSession, example_id: uuid.UUID, obj: Example) -> Example | None:
    existing = await db.get(Example, example_id)
    if existing is None:
        return None
    existing.name = obj.name
    existing.meta = obj.meta
    existing.is_active = obj.is_active
    existing.status = obj.status
    existing.updated_at = obj.updated_at
    await db.flush()
    await db.refresh(existing)
    return existing


async def delete_example(db: AsyncSession, example_id: uuid.UUID) -> bool:
    obj = await db.get(Example, example_id)
    if obj is None:
        return False
    obj.is_active = False
    await db.flush()
    return True
