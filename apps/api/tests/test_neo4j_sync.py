import asyncio
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.models.entity import Entity, EntityRelation
from app.services.neo4j_sync import (
    CREATE_ENTITY_ID_CONSTRAINT,
    UPSERT_ENTITIES,
    UPSERT_RELATIONS,
    ensure_neo4j_constraints,
    serialize_entity,
    serialize_relation,
    sync_postgres_graph_to_neo4j,
)


class FakeNeo4jClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run_write(self, query: str, **parameters: Any) -> None:
        self.calls.append((query, parameters))


class FakeScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class FakeDbResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.rows)


class FakeDbSession:
    def __init__(self, batches: list[list[object]]) -> None:
        self.batches = batches

    async def execute(self, _: object) -> FakeDbResult:
        return FakeDbResult(self.batches.pop(0))


def make_entity(entity_type: str = "phone", display_value: str = "+51999999999") -> Entity:
    entity = Entity(
        type=entity_type,
        raw_value=display_value,
        normalized_value=display_value,
        display_value=display_value,
        metadata_json={"source": "test"},
    )
    entity.id = uuid4()
    entity.created_at = datetime(2026, 5, 31, 12, 0, 0)
    entity.updated_at = datetime(2026, 5, 31, 12, 5, 0)
    return entity


def make_relation(source: Entity, target: Entity) -> EntityRelation:
    relation = EntityRelation(
        source_entity_id=source.id,
        target_entity_id=target.id,
        relation_type="mentioned_in_report",
        evidence={"report_id": "report-1"},
    )
    relation.id = uuid4()
    relation.created_at = datetime(2026, 5, 31, 12, 10, 0)
    relation.updated_at = datetime(2026, 5, 31, 12, 15, 0)
    return relation


def test_ensure_neo4j_constraints_runs_expected_queries() -> None:
    client = FakeNeo4jClient()

    count = asyncio.run(ensure_neo4j_constraints(client))

    assert count == 3
    assert client.calls[0][0] == CREATE_ENTITY_ID_CONSTRAINT
    assert all(parameters == {} for _, parameters in client.calls)


def test_serialize_entity_prepares_neo4j_safe_properties() -> None:
    entity = make_entity()

    payload = serialize_entity(entity)

    assert payload["id"] == str(entity.id)
    assert payload["type"] == "phone"
    assert payload["metadata_json"] == '{"source": "test"}'
    assert payload["created_at"] == "2026-05-31T12:00:00"


def test_serialize_relation_prepares_neo4j_safe_properties() -> None:
    source = make_entity("url", "https://example.test")
    target = make_entity()
    relation = make_relation(source, target)

    payload = serialize_relation(relation)

    assert payload["id"] == str(relation.id)
    assert payload["source_id"] == str(source.id)
    assert payload["target_id"] == str(target.id)
    assert payload["relation_type"] == "mentioned_in_report"
    assert payload["evidence_json"] == '{"report_id": "report-1"}'


def test_sync_postgres_graph_to_neo4j_syncs_entities_then_relations() -> None:
    source = make_entity("url", "https://example.test")
    target = make_entity()
    relation = make_relation(source, target)
    db = FakeDbSession([[source, target], [], [relation], []])
    client = FakeNeo4jClient()

    result = asyncio.run(
        sync_postgres_graph_to_neo4j(
            db,  # type: ignore[arg-type]
            client,
            batch_size=2,
        )
    )

    assert result.entities_synced == 2
    assert result.relations_synced == 1
    assert result.constraints_ensured == 3
    assert client.calls[3][0] == UPSERT_ENTITIES
    assert client.calls[3][1]["entities"][0]["id"] == str(source.id)
    assert client.calls[4][0] == UPSERT_RELATIONS
    assert client.calls[4][1]["relations"][0]["id"] == str(relation.id)
