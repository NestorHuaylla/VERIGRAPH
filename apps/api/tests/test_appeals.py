import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.constants import AppealStatus, ReviewStatus
from app.models.appeal import Appeal
from app.models.notification import Notification, NotificationDelivery
from app.models.report import Report
from app.schemas.appeal import AppealCreate, AppealStatusUpdate
from app.services.appeals import (
    AppealNotFoundError,
    apply_appeal_status_update,
    build_appeal,
    create_report_appeal,
    list_report_appeals,
    mark_report_as_appealed,
    update_appeal_status,
)
from app.services.reports import ReportNotFoundError


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


class FakeAppealSession:
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

    async def flush(self) -> None:
        for obj in self.objects:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj: object) -> None:
        self.refreshed = obj


def build_report() -> Report:
    report = Report(
        entity_id=None,
        reporter_contact=None,
        reason="Promete ganancia garantizada y pide deposito primero.",
        status=ReviewStatus.CONFIRMED.value,
        source="public_form",
        metadata_json={},
    )
    report.id = uuid4()
    report.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    report.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return report


def build_payload() -> AppealCreate:
    return AppealCreate(
        appellant_contact="legal@example.com",
        reason="El reporte es incorrecto y contamos con evidencia para solicitar revision.",
    )


def build_existing_appeal() -> Appeal:
    report = build_report()
    appeal = build_appeal(report.id, build_payload())
    appeal.id = uuid4()
    appeal.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    appeal.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return appeal


def test_mark_report_as_appealed_sets_review_status_and_metadata() -> None:
    report = build_report()

    mark_report_as_appealed(report)

    assert report.status == ReviewStatus.APPEAL.value
    assert report.metadata_json["has_open_appeal"] is True


def test_build_appeal_starts_pending() -> None:
    report_id = uuid4()
    payload = build_payload()

    appeal = build_appeal(report_id, payload)

    assert appeal.report_id == report_id
    assert appeal.appellant_contact == "legal@example.com"
    assert appeal.reason == payload.reason
    assert appeal.status == AppealStatus.PENDING.value
    assert appeal.resolution_reason is None
    assert appeal.metadata_json == {"status_history": []}


def test_create_report_appeal_marks_report_writes_audit_and_commits() -> None:
    report = build_report()
    session = FakeAppealSession([FakeScalarOneResult(report)])

    response = asyncio.run(
        create_report_appeal(
            session,  # type: ignore[arg-type]
            report.id,
            build_payload(),
        )
    )

    assert report.status == ReviewStatus.APPEAL.value
    assert session.committed is True
    assert session.refreshed is session.objects[0]
    assert len(session.objects) == 4
    appeal = session.objects[0]
    audit_log = session.objects[1]
    notification = session.objects[2]
    delivery = session.objects[3]
    assert isinstance(appeal, Appeal)
    assert response.report_id == str(report.id)
    assert response.status == AppealStatus.PENDING
    assert audit_log.action == "report.appeal_created"
    assert audit_log.target_type == "report"
    assert audit_log.target_id == str(report.id)
    assert audit_log.metadata_json["appeal_id"] == str(appeal.id)
    assert audit_log.metadata_json["has_appellant_contact"] is True
    assert isinstance(notification, Notification)
    assert notification.event_type == "appeal.created"
    assert notification.metadata_json["appeal_id"] == str(appeal.id)
    assert notification.metadata_json["report_id"] == str(report.id)
    assert isinstance(delivery, NotificationDelivery)
    assert delivery.notification_id == notification.id
    assert delivery.channel == "webhook"
    assert delivery.status == "pending"


def test_create_report_appeal_raises_when_report_does_not_exist() -> None:
    session = FakeAppealSession([FakeScalarOneResult(None)])

    with pytest.raises(ReportNotFoundError):
        asyncio.run(
            create_report_appeal(
                session,  # type: ignore[arg-type]
                uuid4(),
                build_payload(),
            )
        )

    assert session.committed is False
    assert session.objects == []


def test_list_report_appeals_returns_registered_appeals() -> None:
    report = build_report()
    appeal = build_existing_appeal()
    appeal.report_id = report.id
    session = FakeAppealSession(
        [
            FakeScalarOneResult(report),
            FakeScalarManyResult([appeal]),
        ]
    )

    response = asyncio.run(
        list_report_appeals(
            session,  # type: ignore[arg-type]
            report.id,
        )
    )

    assert len(response) == 1
    assert response[0].id == str(appeal.id)
    assert response[0].report_id == str(report.id)
    assert response[0].status == AppealStatus.PENDING


def test_apply_appeal_status_update_keeps_status_history() -> None:
    appeal = build_existing_appeal()
    payload = AppealStatusUpdate(
        status=AppealStatus.UNDER_REVIEW,
        reason="Analista asignado para revision.",
    )

    old_status, new_status = apply_appeal_status_update(appeal, payload)

    assert old_status == AppealStatus.PENDING.value
    assert new_status == AppealStatus.UNDER_REVIEW
    assert appeal.status == AppealStatus.UNDER_REVIEW.value
    assert appeal.resolution_reason == "Analista asignado para revision."
    assert appeal.metadata_json["status_history"] == [
        {
            "from": "pending",
            "to": "under_review",
            "reason": "Analista asignado para revision.",
        }
    ]


def test_update_appeal_status_writes_audit_log_and_commits() -> None:
    appeal = build_existing_appeal()
    session = FakeAppealSession([FakeScalarOneResult(appeal)])
    payload = AppealStatusUpdate(
        status=AppealStatus.ACCEPTED,
        reason="La evidencia exculpatoria fue validada.",
    )

    response = asyncio.run(
        update_appeal_status(
            session,  # type: ignore[arg-type]
            appeal.id,
            payload,
        )
    )

    assert session.committed is True
    assert session.refreshed is appeal
    assert response.status == AppealStatus.ACCEPTED
    assert response.resolution_reason == "La evidencia exculpatoria fue validada."
    assert len(session.objects) == 1
    audit_log = session.objects[0]
    assert audit_log.action == "appeal.status_changed"
    assert audit_log.target_type == "appeal"
    assert audit_log.target_id == str(appeal.id)
    assert audit_log.metadata_json["report_id"] == str(appeal.report_id)
    assert audit_log.metadata_json["old_status"] == "pending"
    assert audit_log.metadata_json["new_status"] == "accepted"


def test_update_appeal_status_raises_when_appeal_does_not_exist() -> None:
    session = FakeAppealSession([FakeScalarOneResult(None)])
    payload = AppealStatusUpdate(
        status=AppealStatus.REJECTED,
        reason="No se presento evidencia suficiente.",
    )

    with pytest.raises(AppealNotFoundError):
        asyncio.run(
            update_appeal_status(
                session,  # type: ignore[arg-type]
                uuid4(),
                payload,
            )
        )

    assert session.committed is False
    assert session.objects == []
