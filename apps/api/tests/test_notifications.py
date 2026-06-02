import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.constants import NotificationSeverity, RiskLevel
from app.models.appeal import Appeal
from app.models.entity import Entity
from app.models.evidence import EvidenceFile
from app.models.external_reputation import ExternalReputationCheck
from app.models.notification import Notification, NotificationDelivery
from app.models.report import Report
from app.schemas.external_reputation import ExternalReputationSummary
from app.services.notifications import (
    NotificationNotFoundError,
    build_notification_list_item,
    create_appeal_created_notification,
    create_evidence_analysis_notification,
    create_external_reputation_notification,
    create_notification,
    create_report_risk_notification,
    list_notifications,
    mark_notification_read,
)
from app.services.scoring import ScoreResult


class FakeScalarOneResult:
    def __init__(self, item: object | None) -> None:
        self.item = item

    def scalar_one_or_none(self) -> object | None:
        return self.item


class FakeScalarManyResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def scalars(self) -> "FakeScalarManyResult":
        return self

    def all(self) -> list[object]:
        return self.items


class FakeNotificationSession:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.objects: list[object] = []
        self.committed = False
        self.refreshed: object | None = None

    async def execute(self, statement: object) -> object:
        self.statement = statement
        return self.results.pop(0)

    def add(self, obj: object) -> None:
        self.objects.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj: object) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
        self.refreshed = obj


def build_notification() -> Notification:
    notification = Notification(
        user_id=None,
        event_type="case.critical",
        title="Expediente critico detectado",
        message="El expediente quedo en nivel critical.",
        severity=NotificationSeverity.CRITICAL.value,
        is_read=False,
        metadata_json={"case_id": str(uuid4()), "case_score": 40},
    )
    notification.id = uuid4()
    notification.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    notification.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return notification


def build_entity() -> Entity:
    entity = Entity(
        type="url",
        raw_value="https://estafa-peru.com",
        normalized_value="https://estafa-peru.com",
        display_value="https://estafa-peru.com",
        metadata_json={},
    )
    entity.id = uuid4()
    return entity


def build_report(entity: Entity | None = None) -> Report:
    entity = entity or build_entity()
    report = Report(
        entity_id=entity.id,
        reporter_contact=None,
        reason="Promete ganancia garantizada.",
        status="pending",
        source="public_form",
        metadata_json={},
    )
    report.id = uuid4()
    return report


def test_create_notification_adds_unread_notification_without_commit() -> None:
    session = FakeNotificationSession([])
    metadata = {"case_id": str(uuid4()), "case_score": 40}

    notification = asyncio.run(
        create_notification(
            session,  # type: ignore[arg-type]
            event_type="case.critical",
            title="Expediente critico detectado",
            message="El expediente quedo en nivel critical.",
            severity=NotificationSeverity.CRITICAL,
            metadata=metadata,
        )
    )

    assert session.objects == [notification]
    assert session.committed is False
    assert notification.event_type == "case.critical"
    assert notification.severity == NotificationSeverity.CRITICAL.value
    assert notification.is_read is False
    assert notification.metadata_json == metadata


def test_build_notification_list_item_maps_model_to_schema() -> None:
    notification = build_notification()

    item = build_notification_list_item(notification)

    assert item.id == str(notification.id)
    assert item.event_type == "case.critical"
    assert item.severity == NotificationSeverity.CRITICAL
    assert item.is_read is False
    assert item.metadata["case_score"] == 40


def test_list_notifications_returns_items() -> None:
    notification = build_notification()
    session = FakeNotificationSession([FakeScalarManyResult([notification])])

    response = asyncio.run(
        list_notifications(
            session,  # type: ignore[arg-type]
            unread_only=True,
        )
    )

    assert len(response) == 1
    assert response[0].id == str(notification.id)
    assert response[0].title == "Expediente critico detectado"


def test_mark_notification_read_updates_and_commits() -> None:
    notification = build_notification()
    session = FakeNotificationSession([FakeScalarOneResult(notification)])

    response = asyncio.run(
        mark_notification_read(
            session,  # type: ignore[arg-type]
            notification.id,
        )
    )

    assert response is notification
    assert notification.is_read is True
    assert session.committed is True
    assert session.refreshed is notification


def test_mark_notification_read_raises_when_missing() -> None:
    session = FakeNotificationSession([FakeScalarOneResult(None)])

    with pytest.raises(NotificationNotFoundError):
        asyncio.run(
            mark_notification_read(
                session,  # type: ignore[arg-type]
                uuid4(),
            )
        )

    assert session.committed is False


def test_create_report_risk_notification_skips_low_risk() -> None:
    session = FakeNotificationSession([])
    entity = build_entity()
    report = build_report(entity)
    risk = ScoreResult(score=3, level=RiskLevel.LOW, explanation="Bajo.", signals=[])

    notification = asyncio.run(
        create_report_risk_notification(
            session,  # type: ignore[arg-type]
            report=report,
            entity=entity,
            risk=risk,
            relations_created=0,
            graph_degree=0,
        )
    )

    assert notification is None
    assert session.objects == []


def test_create_report_risk_notification_adds_high_risk_alert() -> None:
    session = FakeNotificationSession([])
    entity = build_entity()
    report = build_report(entity)
    risk = ScoreResult(score=22, level=RiskLevel.HIGH, explanation="Alto.", signals=[])

    notification = asyncio.run(
        create_report_risk_notification(
            session,  # type: ignore[arg-type]
            report=report,
            entity=entity,
            risk=risk,
            relations_created=2,
            graph_degree=4,
        )
    )

    assert notification in session.objects
    delivery = session.objects[1]
    assert isinstance(delivery, NotificationDelivery)
    assert delivery.notification_id == notification.id
    assert delivery.status == "pending"
    assert notification.event_type == "report.high_risk"
    assert notification.severity == NotificationSeverity.WARNING.value
    assert notification.metadata_json["report_id"] == str(report.id)
    assert notification.metadata_json["risk_score"] == 22
    assert notification.metadata_json["relations_created"] == 2


def test_create_appeal_created_notification_adds_warning_alert() -> None:
    session = FakeNotificationSession([])
    appeal = Appeal(
        report_id=uuid4(),
        appellant_contact="legal@example.com",
        reason="Solicito revision.",
        status="pending",
        resolution_reason=None,
        metadata_json={},
    )
    appeal.id = uuid4()

    notification = asyncio.run(
        create_appeal_created_notification(
            session,  # type: ignore[arg-type]
            appeal,
        )
    )

    assert notification in session.objects
    delivery = session.objects[1]
    assert isinstance(delivery, NotificationDelivery)
    assert delivery.notification_id == notification.id
    assert delivery.status == "pending"
    assert notification.event_type == "appeal.created"
    assert notification.severity == NotificationSeverity.WARNING.value
    assert notification.metadata_json["appeal_id"] == str(appeal.id)
    assert notification.metadata_json["has_appellant_contact"] is True


def test_create_evidence_analysis_notification_adds_alert_when_entities_were_connected() -> None:
    session = FakeNotificationSession([])
    report = build_report()
    evidence = EvidenceFile(
        report_id=report.id,
        object_key=f"reports/{report.id}/evidence/test.txt",
        filename="evidencia.txt",
        content_type="text/plain",
        sha256="a" * 64,
        metadata_json={},
    )
    evidence.id = uuid4()

    notification = asyncio.run(
        create_evidence_analysis_notification(
            session,  # type: ignore[arg-type]
            evidence=evidence,
            report=report,
            analysis={
                "status": "completed",
                "engine": "plain_text",
                "provider": "local",
                "relation_type": "mentioned_in_evidence",
                "entities_created": 1,
                "relations_created": 1,
            },
        )
    )

    assert notification in session.objects
    delivery = session.objects[1]
    assert isinstance(delivery, NotificationDelivery)
    assert delivery.notification_id == notification.id
    assert delivery.status == "pending"
    assert notification.event_type == "evidence.analysis_completed"
    assert notification.metadata_json["evidence_id"] == str(evidence.id)
    assert notification.metadata_json["entities_created"] == 1
    assert notification.metadata_json["relations_created"] == 1


def test_create_external_reputation_notification_adds_malicious_alert() -> None:
    session = FakeNotificationSession([])
    entity = build_entity()
    check = ExternalReputationCheck(
        entity_id=entity.id,
        source="urlhaus",
        status="malicious",
        malicious=True,
        severity="high",
        summary="URLhaus matched malware.",
        reference="https://urlhaus.abuse.ch/url/1/",
        raw={},
        metadata_json={},
    )
    summary = ExternalReputationSummary(
        malicious=True,
        malicious_sources=["urlhaus"],
        checked_sources=["urlhaus"],
        highest_severity="high",
    )

    notification = asyncio.run(
        create_external_reputation_notification(
            session,  # type: ignore[arg-type]
            entity=entity,
            checks=[check],
            summary=summary,
        )
    )

    assert notification in session.objects
    delivery = session.objects[1]
    assert isinstance(delivery, NotificationDelivery)
    assert delivery.notification_id == notification.id
    assert notification.event_type == "external_reputation.malicious"
    assert notification.severity == NotificationSeverity.WARNING.value
    assert notification.metadata_json["entity_id"] == str(entity.id)
    assert notification.metadata_json["malicious_sources"] == ["urlhaus"]
