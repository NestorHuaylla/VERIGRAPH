from uuid import UUID
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity, EntityRelation
from app.services.entities import get_or_create_entity
from app.services.indicators import ExtractedIndicator, extract_indicators
from app.services.normalizer import normalize_entity

MENTIONED_IN_REPORT = "mentioned_in_report"


@dataclass(frozen=True)
class TextRelationCreationResult:
    relations: list[EntityRelation]
    entities_created: int


async def create_report_entity_relations(
    db: AsyncSession,
    *,
    source_entity: Entity,
    report_id: UUID,
    text: str,
) -> list[EntityRelation]:
    result = await create_entity_relations_from_text(
        db,
        source_entity=source_entity,
        report_id=report_id,
        text=text,
        relation_type=MENTIONED_IN_REPORT,
        indicator_source="report_reason",
    )
    return result.relations


async def create_entity_relations_from_text(
    db: AsyncSession,
    *,
    source_entity: Entity,
    report_id: UUID,
    text: str,
    relation_type: str,
    indicator_source: str,
    evidence_extra: dict | None = None,
) -> TextRelationCreationResult:
    relations: list[EntityRelation] = []
    entities_created = 0
    seen_targets: set[tuple[str, str]] = set()

    for indicator in extract_indicators(text):
        normalized = normalize_entity(indicator.entity_type, indicator.raw_value)
        target_key = (indicator.entity_type.value, normalized.value)
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)

        if source_entity.type == indicator.entity_type.value and source_entity.normalized_value == normalized.value:
            continue

        indicator = ExtractedIndicator(
            entity_type=indicator.entity_type,
            raw_value=indicator.raw_value,
            source=indicator_source,
        )
        resolution = await get_or_create_entity(
            db,
            entity_type=indicator.entity_type,
            raw_value=indicator.raw_value,
            source=indicator_source,
        )
        if resolution.created:
            entities_created += 1

        relation = await create_entity_relation_once(
            db,
            source_entity=source_entity,
            target_entity=resolution.entity,
            report_id=report_id,
            indicator=indicator,
            relation_type=relation_type,
            evidence_extra=evidence_extra,
        )
        if relation:
            relations.append(relation)

    return TextRelationCreationResult(relations=relations, entities_created=entities_created)


async def find_entity_relation(
    db: AsyncSession,
    *,
    source_entity_id: UUID,
    target_entity_id: UUID,
    relation_type: str,
) -> EntityRelation | None:
    result = await db.execute(
        select(EntityRelation).where(
            EntityRelation.source_entity_id == source_entity_id,
            EntityRelation.target_entity_id == target_entity_id,
            EntityRelation.relation_type == relation_type,
        )
    )
    return result.scalar_one_or_none()


async def create_entity_relation_once(
    db: AsyncSession,
    *,
    source_entity: Entity,
    target_entity: Entity,
    report_id: UUID,
    indicator: ExtractedIndicator,
    relation_type: str = MENTIONED_IN_REPORT,
    evidence_extra: dict | None = None,
) -> EntityRelation | None:
    existing = await find_entity_relation(
        db,
        source_entity_id=source_entity.id,
        target_entity_id=target_entity.id,
        relation_type=relation_type,
    )
    if existing:
        return None

    try:
        async with db.begin_nested():
            relation = build_entity_relation(
                source_entity=source_entity,
                target_entity=target_entity,
                report_id=report_id,
                indicator=indicator,
                relation_type=relation_type,
                evidence_extra=evidence_extra,
            )
            db.add(relation)
            await db.flush()
    except IntegrityError:
        existing = await find_entity_relation(
            db,
            source_entity_id=source_entity.id,
            target_entity_id=target_entity.id,
            relation_type=relation_type,
        )
        if existing is None:
            raise
        return None

    return relation


def build_entity_relation(
    *,
    source_entity: Entity,
    target_entity: Entity,
    report_id: UUID,
    indicator: ExtractedIndicator,
    relation_type: str = MENTIONED_IN_REPORT,
    evidence_extra: dict | None = None,
) -> EntityRelation:
    evidence = {
        "report_id": str(report_id),
        "source": indicator.source,
        "raw_value": indicator.raw_value,
        "target_type": indicator.entity_type.value,
    }
    evidence.update(evidence_extra or {})

    return EntityRelation(
        source_entity_id=source_entity.id,
        target_entity_id=target_entity.id,
        relation_type=relation_type,
        evidence=evidence,
    )
