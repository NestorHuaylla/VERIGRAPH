import asyncio
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.core.constants import EntityType
from app.models.entity import Entity, EntityRelation
from app.services.indicators import ExtractedIndicator
from app.services.relations import (
    MENTIONED_IN_REPORT,
    build_entity_relation,
    create_entity_relation_once,
    create_entity_relations_from_text,
    create_report_entity_relations,
)


class FakeResult:
    def __init__(self, result: object | None) -> None:
        self.result = result

    def scalar_one_or_none(self) -> object | None:
        return self.result


class FakeSession:
    def __init__(self, execute_results: list[object | None], raise_integrity_on_flush: bool = False) -> None:
        self.execute_results = execute_results
        self.raise_integrity_on_flush = raise_integrity_on_flush
        self.objects: list[object] = []

    async def execute(self, _: Any) -> FakeResult:
        return FakeResult(self.execute_results.pop(0))

    def add(self, obj: object) -> None:
        self.objects.append(obj)

    async def flush(self) -> None:
        if self.raise_integrity_on_flush:
            raise IntegrityError("insert relation", {}, Exception("duplicate relation"))
        return None

    def begin_nested(self) -> "FakeNestedTransaction":
        return FakeNestedTransaction(self)


class FakeNestedTransaction:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.object_count = len(session.objects)

    async def __aenter__(self) -> "FakeNestedTransaction":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if exc_type is not None:
            del self.session.objects[self.object_count :]
        return False


def make_entity(entity_type: str, normalized_value: str) -> Entity:
    entity = Entity(
        type=entity_type,
        raw_value=normalized_value,
        normalized_value=normalized_value,
        display_value=normalized_value,
        metadata_json={},
    )
    entity.id = uuid4()
    return entity


def test_build_entity_relation_sets_evidence() -> None:
    source = make_entity("url", "https://estafa-peru.com/oferta")
    target = make_entity("phone", "+51999999999")
    report_id = uuid4()

    relation = build_entity_relation(
        source_entity=source,
        target_entity=target,
        report_id=report_id,
        indicator=ExtractedIndicator(entity_type=EntityType.PHONE, raw_value="+51 999 999 999"),
    )

    assert relation.source_entity_id == source.id
    assert relation.target_entity_id == target.id
    assert relation.relation_type == MENTIONED_IN_REPORT
    assert relation.evidence["report_id"] == str(report_id)
    assert relation.evidence["raw_value"] == "+51 999 999 999"


def test_create_report_entity_relations_creates_relations_for_indicators() -> None:
    source = make_entity("url", "https://estafa-peru.com/oferta")
    phone = make_entity("phone", "+51999999999")
    wallet = make_entity("wallet", "evm:0xabcdef1234567890abcdef1234567890abcdef12")
    session = FakeSession(execute_results=[phone, None, wallet, None])
    report_id = uuid4()

    relations = asyncio.run(
        create_report_entity_relations(
            session,  # type: ignore[arg-type]
            source_entity=source,
            report_id=report_id,
            text="+51 999 999 999 y 0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
        )
    )

    assert len(relations) == 2
    assert all(isinstance(relation, EntityRelation) for relation in relations)
    assert relations[0].source_entity_id == source.id
    assert relations[0].target_entity_id == phone.id
    assert relations[1].target_entity_id == wallet.id
    assert session.objects == relations


def test_create_entity_relations_from_text_supports_evidence_relation_type() -> None:
    source = make_entity("url", "https://estafa-peru.com/oferta")
    phone = make_entity("phone", "+51999999999")
    session = FakeSession(execute_results=[phone, None])
    report_id = uuid4()

    result = asyncio.run(
        create_entity_relations_from_text(
            session,  # type: ignore[arg-type]
            source_entity=source,
            report_id=report_id,
            text="+51 999 999 999",
            relation_type="mentioned_in_evidence",
            indicator_source="evidence_analysis",
            evidence_extra={"evidence_id": "evidence-1"},
        )
    )

    assert result.entities_created == 0
    assert len(result.relations) == 1
    relation = result.relations[0]
    assert relation.relation_type == "mentioned_in_evidence"
    assert relation.evidence["source"] == "evidence_analysis"
    assert relation.evidence["evidence_id"] == "evidence-1"


def test_create_entity_relation_once_skips_existing_relation() -> None:
    source = make_entity("url", "https://estafa-peru.com/oferta")
    target = make_entity("phone", "+51999999999")
    existing = build_entity_relation(
        source_entity=source,
        target_entity=target,
        report_id=uuid4(),
        indicator=ExtractedIndicator(entity_type=EntityType.PHONE, raw_value="+51 999 999 999"),
    )
    session = FakeSession(execute_results=[existing])

    relation = asyncio.run(
        create_entity_relation_once(
            session,  # type: ignore[arg-type]
            source_entity=source,
            target_entity=target,
            report_id=uuid4(),
            indicator=ExtractedIndicator(entity_type=EntityType.PHONE, raw_value="wa.me/51999999999"),
        )
    )

    assert relation is None
    assert session.objects == []


def test_create_entity_relation_once_recovers_from_concurrent_duplicate() -> None:
    source = make_entity("url", "https://estafa-peru.com/oferta")
    target = make_entity("phone", "+51999999999")
    existing = build_entity_relation(
        source_entity=source,
        target_entity=target,
        report_id=uuid4(),
        indicator=ExtractedIndicator(entity_type=EntityType.PHONE, raw_value="+51 999 999 999"),
    )
    session = FakeSession(execute_results=[None, existing], raise_integrity_on_flush=True)

    relation = asyncio.run(
        create_entity_relation_once(
            session,  # type: ignore[arg-type]
            source_entity=source,
            target_entity=target,
            report_id=uuid4(),
            indicator=ExtractedIndicator(entity_type=EntityType.PHONE, raw_value="wa.me/51999999999"),
        )
    )

    assert relation is None
    assert session.objects == []


def test_create_report_entity_relations_skips_self_relation() -> None:
    source = make_entity("phone", "+51999999999")
    session = FakeSession(execute_results=[])

    relations = asyncio.run(
        create_report_entity_relations(
            session,  # type: ignore[arg-type]
            source_entity=source,
            report_id=uuid4(),
            text="Contacto +51 999 999 999",
        )
    )

    assert relations == []
    assert session.objects == []
