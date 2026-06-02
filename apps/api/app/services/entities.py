from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EntityType
from app.models.entity import Entity
from app.services.normalizer import NormalizedEntity, normalize_entity


@dataclass(frozen=True)
class EntityResolution:
    entity: Entity
    normalized: NormalizedEntity
    created: bool


async def find_entity_by_normalized_value(
    db: AsyncSession,
    *,
    entity_type: EntityType,
    normalized_value: str,
) -> Entity | None:
    result = await db.execute(
        select(Entity).where(
            Entity.type == entity_type.value,
            Entity.normalized_value == normalized_value,
        )
    )
    return result.scalar_one_or_none()


async def find_entity_by_id(db: AsyncSession, entity_id: object) -> Entity | None:
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    return result.scalar_one_or_none()


async def get_or_create_entity(
    db: AsyncSession,
    *,
    entity_type: EntityType,
    raw_value: str,
    source: str = "unknown",
) -> EntityResolution:
    normalized = normalize_entity(entity_type, raw_value)
    entity = await find_entity_by_normalized_value(
        db,
        entity_type=entity_type,
        normalized_value=normalized.value,
    )

    if entity:
        return EntityResolution(entity=entity, normalized=normalized, created=False)

    try:
        async with db.begin_nested():
            entity = Entity(
                type=entity_type.value,
                raw_value=raw_value,
                normalized_value=normalized.value,
                display_value=normalized.display_value,
                metadata_json={"created_from": source},
            )
            db.add(entity)
            await db.flush()
    except IntegrityError:
        entity = await find_entity_by_normalized_value(
            db,
            entity_type=entity_type,
            normalized_value=normalized.value,
        )
        if entity is None:
            raise
        return EntityResolution(entity=entity, normalized=normalized, created=False)

    return EntityResolution(entity=entity, normalized=normalized, created=True)
