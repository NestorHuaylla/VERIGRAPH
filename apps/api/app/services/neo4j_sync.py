from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from neo4j import AsyncGraphDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.entity import Entity, EntityRelation


CREATE_ENTITY_ID_CONSTRAINT = """
CREATE CONSTRAINT verigraph_entity_id IF NOT EXISTS
FOR (entity:VerigraphEntity)
REQUIRE entity.id IS UNIQUE
"""

CREATE_ENTITY_TYPE_INDEX = """
CREATE INDEX verigraph_entity_type IF NOT EXISTS
FOR (entity:VerigraphEntity)
ON (entity.type)
"""

CREATE_ENTITY_NORMALIZED_INDEX = """
CREATE INDEX verigraph_entity_normalized IF NOT EXISTS
FOR (entity:VerigraphEntity)
ON (entity.normalized_value)
"""

UPSERT_ENTITIES = """
UNWIND $entities AS entity
MERGE (node:VerigraphEntity {id: entity.id})
SET node.type = entity.type,
    node.raw_value = entity.raw_value,
    node.normalized_value = entity.normalized_value,
    node.display_value = entity.display_value,
    node.metadata_json = entity.metadata_json,
    node.created_at = entity.created_at,
    node.updated_at = entity.updated_at
"""

UPSERT_RELATIONS = """
UNWIND $relations AS relation
MATCH (source:VerigraphEntity {id: relation.source_id})
MATCH (target:VerigraphEntity {id: relation.target_id})
MERGE (source)-[edge:VERIGRAPH_RELATION {id: relation.id}]->(target)
SET edge.relation_type = relation.relation_type,
    edge.evidence_json = relation.evidence_json,
    edge.created_at = relation.created_at,
    edge.updated_at = relation.updated_at
"""


class Neo4jWriteClient(Protocol):
    async def run_write(self, query: str, **parameters: Any) -> None:
        pass


class Neo4jReadWriteClient(Neo4jWriteClient, Protocol):
    async def run_read(self, query: str, **parameters: Any) -> list[dict[str, Any]]:
        pass


@dataclass(frozen=True)
class Neo4jSyncResult:
    entities_synced: int
    relations_synced: int
    constraints_ensured: int


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    @classmethod
    def from_settings(cls, settings: Settings) -> "Neo4jGraphStore":
        return cls(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )

    async def close(self) -> None:
        await self._driver.close()

    async def run_write(self, query: str, **parameters: Any) -> None:
        async with self._driver.session() as session:
            result = await session.run(query, **parameters)
            await result.consume()

    async def run_read(self, query: str, **parameters: Any) -> list[dict[str, Any]]:
        async with self._driver.session() as session:
            result = await session.run(query, **parameters)
            return await result.data()


async def sync_postgres_graph_to_neo4j(
    db: AsyncSession,
    client: Neo4jWriteClient,
    *,
    batch_size: int = 500,
) -> Neo4jSyncResult:
    constraints_ensured = await ensure_neo4j_constraints(client)
    entities_synced = await sync_entities(db, client, batch_size=batch_size)
    relations_synced = await sync_entity_relations(db, client, batch_size=batch_size)

    return Neo4jSyncResult(
        entities_synced=entities_synced,
        relations_synced=relations_synced,
        constraints_ensured=constraints_ensured,
    )


async def ensure_neo4j_constraints(client: Neo4jWriteClient) -> int:
    queries = [
        CREATE_ENTITY_ID_CONSTRAINT,
        CREATE_ENTITY_TYPE_INDEX,
        CREATE_ENTITY_NORMALIZED_INDEX,
    ]
    for query in queries:
        await client.run_write(query)
    return len(queries)


async def sync_entities(
    db: AsyncSession,
    client: Neo4jWriteClient,
    *,
    batch_size: int = 500,
) -> int:
    total = 0
    offset = 0

    while True:
        result = await db.execute(
            select(Entity)
            .order_by(Entity.created_at, Entity.id)
            .offset(offset)
            .limit(batch_size)
        )
        entities = list(result.scalars().all())
        if not entities:
            break

        await client.run_write(UPSERT_ENTITIES, entities=[serialize_entity(entity) for entity in entities])
        synced = len(entities)
        total += synced
        offset += synced

    return total


async def sync_entity_relations(
    db: AsyncSession,
    client: Neo4jWriteClient,
    *,
    batch_size: int = 500,
) -> int:
    total = 0
    offset = 0

    while True:
        result = await db.execute(
            select(EntityRelation)
            .order_by(EntityRelation.created_at, EntityRelation.id)
            .offset(offset)
            .limit(batch_size)
        )
        relations = list(result.scalars().all())
        if not relations:
            break

        await client.run_write(
            UPSERT_RELATIONS,
            relations=[serialize_relation(relation) for relation in relations],
        )
        synced = len(relations)
        total += synced
        offset += synced

    return total


def serialize_entity(entity: Entity) -> dict[str, Any]:
    return {
        "id": str(entity.id),
        "type": entity.type,
        "raw_value": entity.raw_value,
        "normalized_value": entity.normalized_value,
        "display_value": entity.display_value,
        "metadata_json": json.dumps(entity.metadata_json or {}, sort_keys=True),
        "created_at": serialize_datetime(entity.created_at),
        "updated_at": serialize_datetime(entity.updated_at),
    }


def serialize_relation(relation: EntityRelation) -> dict[str, Any]:
    return {
        "id": str(relation.id),
        "source_id": str(relation.source_entity_id),
        "target_id": str(relation.target_entity_id),
        "relation_type": relation.relation_type,
        "evidence_json": json.dumps(relation.evidence or {}, sort_keys=True),
        "created_at": serialize_datetime(relation.created_at),
        "updated_at": serialize_datetime(relation.updated_at),
    }


def serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
