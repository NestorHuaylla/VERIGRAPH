import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.models.audit import AuditLog
from app.services.audit import build_audit_log_response, list_report_audit_logs, write_audit_log


class FakeSession:
    def __init__(self) -> None:
        self.objects: list[object] = []

    def add(self, obj: object) -> None:
        self.objects.append(obj)


class FakeScalarResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def scalars(self) -> "FakeScalarResult":
        return self

    def all(self) -> list[object]:
        return self.items


class FakeReadSession:
    def __init__(self, items: list[object]) -> None:
        self.items = items
        self.statement: object | None = None

    async def execute(self, statement: object) -> FakeScalarResult:
        self.statement = statement
        return FakeScalarResult(self.items)


def build_audit_log(*, target_id: str = "report-1") -> AuditLog:
    audit_log = AuditLog(
        actor_user_id=None,
        action="report.status_changed",
        target_type="report",
        target_id=target_id,
        metadata_json={
            "old_status": "pending",
            "new_status": "confirmed",
            "reason": "Evidencia validada por analista.",
        },
    )
    audit_log.id = uuid4()
    audit_log.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return audit_log


def test_write_audit_log_adds_audit_model() -> None:
    session = FakeSession()

    audit_log = asyncio.run(
        write_audit_log(
            session,  # type: ignore[arg-type]
            actor_user_id=None,
            action="report.created",
            target_type="report",
            target_id="report-1",
            metadata={"risk_level": "medium"},
        )
    )

    assert isinstance(audit_log, AuditLog)
    assert session.objects == [audit_log]
    assert audit_log.action == "report.created"
    assert audit_log.target_type == "report"
    assert audit_log.target_id == "report-1"
    assert audit_log.metadata_json == {"risk_level": "medium"}


def test_build_audit_log_response_maps_public_fields() -> None:
    audit_log = build_audit_log()

    response = build_audit_log_response(audit_log)

    assert response.id == str(audit_log.id)
    assert response.actor_user_id is None
    assert response.action == "report.status_changed"
    assert response.target_type == "report"
    assert response.target_id == "report-1"
    assert response.metadata["new_status"] == "confirmed"
    assert response.created_at == audit_log.created_at


def test_list_report_audit_logs_returns_report_history() -> None:
    report_id = uuid4()
    audit_log = build_audit_log(target_id=str(report_id))
    session = FakeReadSession([audit_log])

    response = asyncio.run(
        list_report_audit_logs(
            session,  # type: ignore[arg-type]
            report_id,
        )
    )

    assert session.statement is not None
    assert len(response) == 1
    assert response[0].target_type == "report"
    assert response[0].target_id == str(report_id)
    assert response[0].metadata["reason"] == "Evidencia validada por analista."
