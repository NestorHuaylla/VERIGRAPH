import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.constants import EntityType, ReviewStatus
from app.models.entity import Entity
from app.schemas.report import ReportCreate, ReportStatusUpdate
from app.services.entities import EntityResolution
from app.services.normalizer import normalize_entity
from app.services.reports import (
    ReportNotFoundError,
    apply_report_status_update,
    build_report,
    build_report_detail,
    build_report_list_item,
    build_risk_score,
    get_report_detail,
    update_report_initial_risk,
    update_report_status,
    write_report_created_audit_log,
)
from app.services.scoring import RULES_VERSION, calculate_initial_score


class FakeSession:
    def __init__(self) -> None:
        self.objects: list[object] = []

    def add(self, obj: object) -> None:
        self.objects.append(obj)


class FakeUpdateResult:
    def __init__(self, report: object | None) -> None:
        self.report = report

    def scalar_one_or_none(self) -> object | None:
        return self.report


class FakeUpdateSession(FakeSession):
    def __init__(self, report: object | None) -> None:
        super().__init__()
        self.report = report
        self.committed = False
        self.refreshed: object | None = None

    async def execute(self, statement: object) -> FakeUpdateResult:
        self.statement = statement
        return FakeUpdateResult(self.report)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj: object) -> None:
        self.refreshed = obj


class FakeReportEntityResult:
    def __init__(self, row: object | None) -> None:
        self.row = row

    def one_or_none(self) -> object | None:
        return self.row


class FakeRiskScoreResult:
    def __init__(self, risk_score: object | None) -> None:
        self.risk_score = risk_score

    def scalar_one_or_none(self) -> object | None:
        return self.risk_score


class FakeDetailSession:
    def __init__(self, row: object | None, risk_score: object | None = None) -> None:
        self.results = [
            FakeReportEntityResult(row),
            FakeRiskScoreResult(risk_score),
        ]
        self.calls = 0

    async def execute(self, statement: object) -> object:
        self.statement = statement
        self.calls += 1
        return self.results.pop(0)


def build_resolution(*, created: bool = True) -> EntityResolution:
    entity = Entity(
        type="url",
        raw_value="https://www.estafa-peru.com/oferta",
        normalized_value="https://estafa-peru.com/oferta",
        display_value="https://estafa-peru.com/oferta",
        metadata_json={"created_from": "test"},
    )
    entity.id = uuid4()

    return EntityResolution(
        entity=entity,
        normalized=normalize_entity(EntityType.URL, "https://www.estafa-peru.com/oferta"),
        created=created,
    )


def test_build_report_sets_initial_metadata() -> None:
    payload = ReportCreate(
        entity_type=EntityType.URL,
        entity_value="https://www.estafa-peru.com/oferta",
        reason="Promete ganancia garantizada y pide deposito primero.",
        reporter_contact="demo@example.com",
    )
    resolution = build_resolution()
    risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
    )

    report = build_report(payload, resolution, risk, source="public_form")

    assert report.entity_id == resolution.entity.id
    assert report.reporter_contact == "demo@example.com"
    assert report.status == "pending"
    assert report.source == "public_form"
    assert report.metadata_json["entity_raw_value"] == payload.entity_value
    assert report.metadata_json["entity_normalized_value"] == "https://estafa-peru.com/oferta"
    assert report.metadata_json["initial_risk_score"] == risk.score
    assert report.metadata_json["initial_risk_level"] == risk.level.value


def test_build_report_merges_request_metadata() -> None:
    payload = ReportCreate(
        entity_type=EntityType.URL,
        entity_value="https://www.estafa-peru.com/oferta",
        reason="Promete ganancia garantizada y pide deposito primero.",
    )
    resolution = build_resolution()
    risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
    )
    report = build_report(
        payload,
        resolution,
        risk,
        source="public_form",
        request_metadata={
            "anti_abuse": {
                "client_ip": "203.0.113.10",
                "user_agent": "pytest-browser",
                "source": "public_form",
            }
        },
    )

    assert report.metadata_json["entity_normalized_value"] == "https://estafa-peru.com/oferta"
    assert report.metadata_json["anti_abuse"] == {
        "client_ip": "203.0.113.10",
        "user_agent": "pytest-browser",
        "source": "public_form",
    }


def test_build_risk_score_uses_rules_version_and_signals() -> None:
    payload = ReportCreate(
        entity_type=EntityType.WALLET,
        entity_value="0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
        reason="Pide pago con wallet crypto.",
    )
    resolution = build_resolution()
    risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value="evm:0xabcdef1234567890abcdef1234567890abcdef12",
    )

    risk_score = build_risk_score(resolution.entity, risk)

    assert risk_score.entity_id == resolution.entity.id
    assert risk_score.score == risk.score
    assert risk_score.level == risk.level.value
    assert risk_score.rules_version == RULES_VERSION
    assert risk_score.signals["items"]


def test_update_report_initial_risk_replaces_metadata_score() -> None:
    payload = ReportCreate(
        entity_type=EntityType.URL,
        entity_value="https://www.estafa-peru.com/oferta",
        reason="Promete ganancia garantizada y pide deposito primero.",
    )
    resolution = build_resolution()
    base_risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
    )
    graph_risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
        graph_degree=3,
    )
    report = build_report(payload, resolution, base_risk, source="public_form")

    update_report_initial_risk(report, graph_risk)

    assert report.metadata_json["initial_risk_score"] == graph_risk.score
    assert report.metadata_json["initial_risk_level"] == graph_risk.level.value


def test_build_report_list_item_uses_latest_risk_score() -> None:
    payload = ReportCreate(
        entity_type=EntityType.URL,
        entity_value="https://www.estafa-peru.com/oferta",
        reason="Promete ganancia garantizada y pide deposito primero.",
    )
    resolution = build_resolution()
    risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
    )
    report = build_report(payload, resolution, risk, source="public_form")
    report.id = uuid4()
    report.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    risk_score = build_risk_score(resolution.entity, risk)

    item = build_report_list_item(report, resolution.entity, risk_score)

    assert item.id == str(report.id)
    assert item.entity_id == str(resolution.entity.id)
    assert item.entity_type == EntityType.URL
    assert item.entity_value == "https://estafa-peru.com/oferta"
    assert item.entity_normalized_value == "https://estafa-peru.com/oferta"
    assert item.status == "pending"
    assert item.risk_score == risk.score
    assert item.risk_level == risk.level
    assert item.created_at == report.created_at


def test_build_report_list_item_falls_back_to_report_metadata() -> None:
    payload = ReportCreate(
        entity_type=EntityType.URL,
        entity_value="https://www.estafa-peru.com/oferta",
        reason="Promete ganancia garantizada y pide deposito primero.",
    )
    resolution = build_resolution()
    risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
    )
    report = build_report(payload, resolution, risk, source="public_form")
    report.id = uuid4()
    report.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)

    item = build_report_list_item(report, resolution.entity, None)

    assert item.risk_score == report.metadata_json["initial_risk_score"]
    assert item.risk_level == risk.level


def test_build_report_detail_uses_entity_risk_and_metadata() -> None:
    payload = ReportCreate(
        entity_type=EntityType.URL,
        entity_value="https://www.estafa-peru.com/oferta",
        reason="Promete ganancia garantizada y pide deposito primero.",
        reporter_contact="demo@example.com",
    )
    resolution = build_resolution()
    risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
    )
    report = build_report(payload, resolution, risk, source="public_form")
    report.id = uuid4()
    report.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    report.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    risk_score = build_risk_score(resolution.entity, risk)

    detail = build_report_detail(report, resolution.entity, risk_score)

    assert detail.id == str(report.id)
    assert detail.entity_id == str(resolution.entity.id)
    assert detail.entity_type == EntityType.URL
    assert detail.entity_value == "https://estafa-peru.com/oferta"
    assert detail.entity_raw_value == "https://www.estafa-peru.com/oferta"
    assert detail.entity_normalized_value == "https://estafa-peru.com/oferta"
    assert detail.reporter_contact == "demo@example.com"
    assert detail.reason == payload.reason
    assert detail.status == ReviewStatus.PENDING
    assert detail.source == "public_form"
    assert detail.risk_score == risk.score
    assert detail.risk_level == risk.level
    assert detail.risk_explanation == risk.explanation
    assert detail.risk_signals
    assert detail.risk_rules_version == RULES_VERSION
    assert detail.metadata["entity_normalized_value"] == "https://estafa-peru.com/oferta"


def test_get_report_detail_returns_latest_risk_context() -> None:
    payload = ReportCreate(
        entity_type=EntityType.URL,
        entity_value="https://www.estafa-peru.com/oferta",
        reason="Promete ganancia garantizada y pide deposito primero.",
    )
    resolution = build_resolution()
    risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
    )
    report = build_report(payload, resolution, risk, source="public_form")
    report.id = uuid4()
    report.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    report.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    risk_score = build_risk_score(resolution.entity, risk)
    session = FakeDetailSession((report, resolution.entity), risk_score)

    detail = asyncio.run(
        get_report_detail(
            session,  # type: ignore[arg-type]
            report.id,
        )
    )

    assert session.calls == 2
    assert detail.id == str(report.id)
    assert detail.risk_score == risk.score
    assert detail.risk_level == risk.level


def test_get_report_detail_raises_when_report_does_not_exist() -> None:
    session = FakeDetailSession(None)

    with pytest.raises(ReportNotFoundError):
        asyncio.run(
            get_report_detail(
                session,  # type: ignore[arg-type]
                uuid4(),
            )
        )

    assert session.calls == 1


def test_apply_report_status_update_keeps_status_history() -> None:
    payload = ReportCreate(
        entity_type=EntityType.URL,
        entity_value="https://www.estafa-peru.com/oferta",
        reason="Promete ganancia garantizada y pide deposito primero.",
    )
    resolution = build_resolution()
    risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
    )
    report = build_report(payload, resolution, risk, source="public_form")
    status_payload = ReportStatusUpdate(
        status=ReviewStatus.CONFIRMED,
        reason="Evidencia validada por analista.",
    )

    old_status, new_status = apply_report_status_update(report, status_payload)

    assert old_status == "pending"
    assert new_status == ReviewStatus.CONFIRMED
    assert report.status == "confirmed"
    assert report.metadata_json["last_status_reason"] == "Evidencia validada por analista."
    assert report.metadata_json["status_history"] == [
        {
            "from": "pending",
            "to": "confirmed",
            "reason": "Evidencia validada por analista.",
        }
    ]


def test_update_report_status_writes_audit_log_and_commits() -> None:
    payload = ReportCreate(
        entity_type=EntityType.URL,
        entity_value="https://www.estafa-peru.com/oferta",
        reason="Promete ganancia garantizada y pide deposito primero.",
    )
    resolution = build_resolution()
    risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
    )
    report = build_report(payload, resolution, risk, source="public_form")
    report.id = uuid4()
    session = FakeUpdateSession(report)
    status_payload = ReportStatusUpdate(
        status=ReviewStatus.FALSE_POSITIVE,
        reason="La evidencia enviada no sostiene el reporte.",
    )

    updated_report = asyncio.run(
        update_report_status(
            session,  # type: ignore[arg-type]
            report.id,
            status_payload,
        )
    )

    assert updated_report is report
    assert report.status == "false_positive"
    assert session.committed is True
    assert session.refreshed is report
    assert len(session.objects) == 1
    audit_log = session.objects[0]
    assert audit_log.action == "report.status_changed"
    assert audit_log.target_type == "report"
    assert audit_log.target_id == str(report.id)
    assert audit_log.metadata_json == {
        "old_status": "pending",
        "new_status": "false_positive",
        "reason": "La evidencia enviada no sostiene el reporte.",
    }


def test_update_report_status_raises_when_report_does_not_exist() -> None:
    session = FakeUpdateSession(None)
    status_payload = ReportStatusUpdate(
        status=ReviewStatus.CONFIRMED,
        reason="Evidencia validada por analista.",
    )

    with pytest.raises(ReportNotFoundError):
        asyncio.run(
            update_report_status(
                session,  # type: ignore[arg-type]
                uuid4(),
                status_payload,
            )
        )

    assert session.committed is False
    assert session.objects == []


def test_write_report_created_audit_log_adds_audit_log() -> None:
    payload = ReportCreate(
        entity_type=EntityType.URL,
        entity_value="https://www.estafa-peru.com/oferta",
        reason="Promete ganancia garantizada y pide deposito primero.",
    )
    resolution = build_resolution(created=False)
    risk = calculate_initial_score(
        text=payload.reason,
        entity_type=payload.entity_type,
        normalized_value=resolution.normalized.value,
    )
    report = build_report(payload, resolution, risk, source="public_form")
    report.id = uuid4()
    session = FakeSession()

    asyncio.run(
        write_report_created_audit_log(
            session,  # type: ignore[arg-type]
            payload,
            resolution,
            risk,
            report,
            graph_degree=3,
            source="public_form",
        )
    )

    assert len(session.objects) == 1
    audit_log = session.objects[0]
    assert audit_log.action == "report.created"
    assert audit_log.target_type == "report"
    assert audit_log.target_id == str(report.id)
    assert audit_log.metadata_json["entity_created"] is False
    assert audit_log.metadata_json["graph_degree"] == 3
    assert audit_log.metadata_json["entity_normalized_value"] == "https://estafa-peru.com/oferta"
