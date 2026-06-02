import asyncio
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.constants import EntityType
from app.models.entity import Entity
from app.services.entities import get_or_create_entity


class FakeResult:
    def __init__(self, entity: Entity | None) -> None:
        self.entity = entity

    def scalar_one_or_none(self) -> Entity | None:
        return self.entity


class FakeSession:
    def __init__(
        self,
        existing_entity: Entity | None = None,
        execute_results: list[Entity | None] | None = None,
        raise_integrity_on_flush: bool = False,
    ) -> None:
        self.execute_results = execute_results
        self.existing_entity = existing_entity
        self.raise_integrity_on_flush = raise_integrity_on_flush
        self.objects: list[object] = []
        self.execute_count = 0
        self.flushed = False

    async def execute(self, _: Any) -> FakeResult:
        self.execute_count += 1
        if self.execute_results is not None and self.execute_results:
            return FakeResult(self.execute_results.pop(0))
        return FakeResult(self.existing_entity)

    def add(self, obj: object) -> None:
        self.objects.append(obj)

    async def flush(self) -> None:
        self.flushed = True
        if self.raise_integrity_on_flush:
            raise IntegrityError("insert entity", {}, Exception("duplicate entity"))

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


def test_get_or_create_entity_reuses_existing_entity() -> None:
    existing = Entity(
        type="phone",
        raw_value="+51 999 999 999",
        normalized_value="+51999999999",
        display_value="+51999999999",
        metadata_json={"created_from": "test"},
    )
    session = FakeSession(existing_entity=existing)

    resolution = asyncio.run(
        get_or_create_entity(
            session,  # type: ignore[arg-type]
            entity_type=EntityType.PHONE,
            raw_value="wa.me/51999999999",
            source="public_report",
        )
    )

    assert resolution.entity is existing
    assert resolution.normalized.value == "+51999999999"
    assert resolution.created is False
    assert session.objects == []
    assert session.execute_count == 1
    assert session.flushed is False


def test_get_or_create_entity_creates_new_entity() -> None:
    session = FakeSession()

    resolution = asyncio.run(
        get_or_create_entity(
            session,  # type: ignore[arg-type]
            entity_type=EntityType.DOMAIN,
            raw_value="https://www.Estafa-Peru.com/oferta",
            source="public_report",
        )
    )

    assert resolution.created is True
    assert resolution.normalized.value == "estafa-peru.com"
    assert resolution.entity.type == "domain"
    assert resolution.entity.raw_value == "https://www.Estafa-Peru.com/oferta"
    assert resolution.entity.normalized_value == "estafa-peru.com"
    assert resolution.entity.metadata_json == {"created_from": "public_report"}
    assert session.objects == [resolution.entity]
    assert session.execute_count == 1
    assert session.flushed is True


def test_get_or_create_entity_recovers_from_concurrent_duplicate() -> None:
    existing = Entity(
        type="phone",
        raw_value="+51 999 999 999",
        normalized_value="+51999999999",
        display_value="+51999999999",
        metadata_json={"created_from": "other_request"},
    )
    session = FakeSession(
        execute_results=[None, existing],
        raise_integrity_on_flush=True,
    )

    resolution = asyncio.run(
        get_or_create_entity(
            session,  # type: ignore[arg-type]
            entity_type=EntityType.PHONE,
            raw_value="wa.me/51999999999",
            source="public_report",
        )
    )

    assert resolution.entity is existing
    assert resolution.normalized.value == "+51999999999"
    assert resolution.created is False
    assert session.objects == []
    assert session.execute_count == 2
    assert session.flushed is True
