import asyncio
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.models.entity import Entity
from app.models.external_reputation import ExternalReputationCheck
from app.models.notification import Notification, NotificationDelivery
from app.schemas.external_reputation import ExternalReputationBatchCreate, ExternalReputationCheckCreate
from app.services.external_reputation import (
    build_external_reputation_check,
    build_external_reputation_response,
    build_external_reputation_summary,
    build_external_risk_signals,
    create_external_reputation_checks,
)


class FakeResult:
    def __init__(self, result: object | None) -> None:
        self.result = result

    def scalar_one_or_none(self) -> object | None:
        return self.result


class FakeSession:
    def __init__(self, entity: Entity | None) -> None:
        self.entity = entity
        self.objects: list[object] = []
        self.committed = False
        self.refreshed: list[object] = []

    async def execute(self, _: Any) -> FakeResult:
        return FakeResult(self.entity)

    def add(self, obj: object) -> None:
        self.objects.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj: object) -> None:
        self.refreshed.append(obj)


def make_entity() -> Entity:
    entity = Entity(
        type="url",
        raw_value="https://bad.test/",
        normalized_value="https://bad.test",
        display_value="https://bad.test",
        metadata_json={},
    )
    entity.id = uuid4()
    return entity


def make_check(source: str, malicious: bool, severity: str) -> ExternalReputationCheck:
    check = ExternalReputationCheck(
        entity_id=uuid4(),
        source=source,
        status="malicious" if malicious else "clean",
        malicious=malicious,
        severity=severity,
        summary=f"{source} summary",
        reference=None,
        raw={},
        metadata_json={},
    )
    check.id = uuid4()
    check.created_at = datetime(2026, 6, 1, 12, 0, 0)
    return check


def test_build_external_reputation_check_merges_metadata() -> None:
    entity = make_entity()
    payload = ExternalReputationCheckCreate(
        source="urlhaus",
        status="malicious",
        malicious=True,
        severity="high",
        summary="URLhaus matched malware.",
        reference="https://urlhaus.abuse.ch/url/1/",
        raw={"query_status": "ok"},
        metadata={"task_id": "task-1"},
    )

    check = build_external_reputation_check(entity, payload, batch_metadata={"worker": "external"})

    assert check.entity_id == entity.id
    assert check.source == "urlhaus"
    assert check.malicious is True
    assert check.metadata_json == {"worker": "external", "task_id": "task-1"}


def test_build_external_reputation_summary_groups_sources() -> None:
    checks = [
        make_check("urlhaus", malicious=True, severity="high"),
        make_check("safe_browsing", malicious=False, severity="none"),
    ]

    summary = build_external_reputation_summary(checks)

    assert summary.malicious is True
    assert summary.malicious_sources == ["urlhaus"]
    assert summary.checked_sources == ["safe_browsing", "urlhaus"]
    assert summary.highest_severity == "high"


def test_build_external_risk_signals_weights_high_confidence_matches() -> None:
    signals = build_external_risk_signals(
        [
            make_check("urlhaus", malicious=True, severity="high"),
            make_check("safe_browsing", malicious=True, severity="medium"),
        ]
    )

    assert [signal.code for signal in signals] == [
        "external_high_confidence_match",
        "external_reputation_match",
    ]
    assert sum(signal.weight for signal in signals) == 28


def test_create_external_reputation_checks_persists_batch() -> None:
    entity = make_entity()
    session = FakeSession(entity)
    payload = ExternalReputationBatchCreate(
        checks=[
            ExternalReputationCheckCreate(
                source="safe_browsing",
                status="clean",
                malicious=False,
                severity="none",
                summary="No matches.",
            )
        ],
        metadata={"task_id": "task-1"},
    )

    result = asyncio.run(
        create_external_reputation_checks(
            session,  # type: ignore[arg-type]
            entity.id,
            payload,
        )
    )

    assert len(result.checks) == 1
    assert session.objects == result.checks
    assert session.committed is True
    assert session.refreshed == result.checks
    assert result.summary.malicious is False


def test_create_external_reputation_checks_alerts_on_malicious_batch() -> None:
    entity = make_entity()
    session = FakeSession(entity)
    payload = ExternalReputationBatchCreate(
        checks=[
            ExternalReputationCheckCreate(
                source="urlhaus",
                status="malicious",
                malicious=True,
                severity="high",
                summary="URLhaus matched malware.",
                reference="https://urlhaus.abuse.ch/url/1/",
            )
        ],
        metadata={"task_id": "task-1"},
    )

    result = asyncio.run(
        create_external_reputation_checks(
            session,  # type: ignore[arg-type]
            entity.id,
            payload,
        )
    )

    assert result.summary.malicious is True
    assert len(result.checks) == 1
    notification = session.objects[1]
    delivery = session.objects[2]
    assert isinstance(notification, Notification)
    assert isinstance(delivery, NotificationDelivery)
    assert notification.event_type == "external_reputation.malicious"
    assert notification.metadata_json["malicious_sources"] == ["urlhaus"]
    assert delivery.notification_id == notification.id


def test_build_external_reputation_response_uses_public_metadata_name() -> None:
    check = make_check("urlhaus", malicious=True, severity="high")
    check.raw = {"query_status": "ok"}
    check.metadata_json = {"task_id": "task-1"}

    response = build_external_reputation_response(check)

    assert response.id == check.id
    assert response.metadata == {"task_id": "task-1"}
    assert response.raw == {"query_status": "ok"}
