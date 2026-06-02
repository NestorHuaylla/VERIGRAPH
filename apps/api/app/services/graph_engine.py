from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.entity import Entity, EntityRelation
from app.schemas.graph import GraphEdge, GraphMetrics, GraphNode, GraphResponse


async def build_graph_preview(db: AsyncSession, *, limit: int = 100) -> GraphResponse:
    source_entity = aliased(Entity)
    target_entity = aliased(Entity)
    statement = (
        select(EntityRelation, source_entity, target_entity)
        .join(source_entity, EntityRelation.source_entity_id == source_entity.id)
        .join(target_entity, EntityRelation.target_entity_id == target_entity.id)
        .limit(limit)
    )
    result = await db.execute(statement)
    return build_graph_from_relation_rows(result.all())


async def build_entity_graph(db: AsyncSession, *, entity_id: UUID, limit: int = 100) -> GraphResponse:
    source_entity = aliased(Entity)
    target_entity = aliased(Entity)
    statement = (
        select(EntityRelation, source_entity, target_entity)
        .join(source_entity, EntityRelation.source_entity_id == source_entity.id)
        .join(target_entity, EntityRelation.target_entity_id == target_entity.id)
        .where(
            or_(
                EntityRelation.source_entity_id == entity_id,
                EntityRelation.target_entity_id == entity_id,
            )
        )
        .limit(limit)
    )
    result = await db.execute(statement)
    return build_graph_from_relation_rows(result.all())


async def calculate_entity_graph_metrics(db: AsyncSession, *, entity_id: UUID) -> GraphMetrics:
    outgoing_result = await db.execute(
        select(func.count(EntityRelation.id)).where(EntityRelation.source_entity_id == entity_id)
    )
    incoming_result = await db.execute(
        select(func.count(EntityRelation.id)).where(EntityRelation.target_entity_id == entity_id)
    )
    outgoing = int(outgoing_result.scalar_one())
    incoming = int(incoming_result.scalar_one())
    return build_graph_metrics(entity_id=entity_id, incoming=incoming, outgoing=outgoing)


def build_graph_metrics(*, entity_id: UUID, incoming: int, outgoing: int) -> GraphMetrics:
    return GraphMetrics(
        entity_id=str(entity_id),
        degree=incoming + outgoing,
        incoming=incoming,
        outgoing=outgoing,
    )


def build_graph_from_relation_rows(rows: list[tuple[EntityRelation, Entity, Entity]]) -> GraphResponse:
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    for relation, source_entity, target_entity in rows:
        source_node = build_graph_node(source_entity)
        target_node = build_graph_node(target_entity)
        nodes[source_node.id] = source_node
        nodes[target_node.id] = target_node
        edges.append(build_graph_edge(relation))

    return GraphResponse(nodes=list(nodes.values()), edges=edges)


def build_graph_node(entity: Entity) -> GraphNode:
    return GraphNode(
        id=str(entity.id),
        label=entity.display_value,
        type=entity.type,
    )


def build_graph_edge(relation: EntityRelation) -> GraphEdge:
    return GraphEdge(
        id=str(relation.id),
        source=str(relation.source_entity_id),
        target=str(relation.target_entity_id),
        type=relation.relation_type,
        evidence=relation.evidence or {},
    )
