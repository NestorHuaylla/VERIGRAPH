import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.constants import CaseStatus, EntityType, RiskLevel
from app.models.case import Case
from app.models.entity import Entity
from app.models.notification import Notification, NotificationDelivery
from app.models.risk import RiskScore
from app.schemas.case import CaseCreate, CaseStatusUpdate
from app.schemas.graph import GraphMetrics, GraphResponse
from app.services.cases import (
    CaseNotFoundError,
    EntityNotFoundError,
    apply_case_status_update,
    build_case_detail,
    build_case_from_entity,
    build_case_list_item,
    build_case_report_item,
    apply_case_snapshot,
    build_case_snapshot,
    create_case_from_entity,
    get_case_root_entity_id,
    list_cases,
    sync_case_snapshot,
    update_case_status,
)


class FakeScalarOneResult:
    def __init__(self, item: object | None) -> None:
        self.item = item

    def scalar_one_or_none(self) -> object | None:
        return self.item

    def scalar_one(self) -> object:
        return self.item


class FakeScalarManyResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def scalars(self) -> "FakeScalarManyResult":
        return self

    def all(self) -> list[object]:
        return self.items


class FakeCaseSession:
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
            if getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj: object) -> None:
        self.refreshed = obj


def build_entity() -> Entity:
    entity = Entity(
        type=EntityType.URL.value,
        raw_value="https://estafa-peru.com",
        normalized_value="https://estafa-peru.com",
        display_value="https://estafa-peru.com",
        metadata_json={},
    )
    entity.id = uuid4()
    entity.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    entity.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return entity


def build_risk_score(entity: Entity) -> RiskScore:
    risk_score = RiskScore(
        entity_id=entity.id,
        score=77,
        level=RiskLevel.HIGH.value,
        explanation="Riesgo alto por reportes relacionados.",
        signals={"items": []},
        rules_version="v1",
    )
    risk_score.id = uuid4()
    risk_score.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return risk_score


def build_case(entity: Entity | None = None) -> Case:
    entity = entity or build_entity()
    case = build_case_from_entity(entity, build_risk_score(entity), CaseCreate(summary="Caso inicial."))
    case.id = uuid4()
    case.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    case.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return case


def test_build_case_from_entity_uses_latest_risk_and_root_metadata() -> None:
    entity = build_entity()
    risk_score = build_risk_score(entity)

    case = build_case_from_entity(
        entity,
        risk_score,
        CaseCreate(title="Caso phishing", summary="Investigacion inicial."),
    )

    assert case.title == "Caso phishing"
    assert case.summary == "Investigacion inicial."
    assert case.status == CaseStatus.OPEN.value
    assert case.risk_level == RiskLevel.HIGH.value
    assert case.metadata_json["root_entity_id"] == str(entity.id)
    assert case.metadata_json["initial_risk_score"] == 77


def test_build_case_from_entity_falls_back_to_medium_risk() -> None:
    entity = build_entity()

    case = build_case_from_entity(entity, None, CaseCreate())

    assert case.risk_level == RiskLevel.MEDIUM.value
    assert case.metadata_json["initial_risk_score"] is None


def test_create_case_from_entity_writes_audit_log_and_commits() -> None:
    actor_user_id = uuid4()
    entity = build_entity()
    risk_score = build_risk_score(entity)
    session = FakeCaseSession([FakeScalarOneResult(entity), FakeScalarOneResult(None), FakeScalarOneResult(risk_score)])

    case = asyncio.run(
        create_case_from_entity(
            session,  # type: ignore[arg-type]
            entity.id,
            CaseCreate(summary="Investigacion inicial."),
            actor_user_id=actor_user_id,
        )
    )

    assert session.committed is True
    assert session.refreshed is case
    assert len(session.objects) == 2
    audit_log = session.objects[1]
    assert audit_log.actor_user_id == actor_user_id
    assert audit_log.action == "case.created"
    assert audit_log.target_type == "case"
    assert audit_log.target_id == str(case.id)
    assert audit_log.metadata_json["root_entity_id"] == str(entity.id)
    assert audit_log.metadata_json["risk_level"] == RiskLevel.HIGH.value


def test_create_case_from_entity_reuses_existing_case() -> None:
    actor_user_id = uuid4()
    entity = build_entity()
    existing_case = build_case(entity)
    session = FakeCaseSession([FakeScalarOneResult(entity), FakeScalarOneResult(existing_case)])

    case = asyncio.run(
        create_case_from_entity(
            session,  # type: ignore[arg-type]
            entity.id,
            CaseCreate(summary="No debe crear otro."),
            actor_user_id=actor_user_id,
        )
    )

    assert case is existing_case
    assert session.committed is True
    assert session.refreshed is existing_case
    assert len(session.objects) == 1
    audit_log = session.objects[0]
    assert audit_log.actor_user_id == actor_user_id
    assert audit_log.action == "case.reused"
    assert audit_log.target_type == "case"
    assert audit_log.target_id == str(existing_case.id)


def test_create_case_from_entity_raises_when_entity_does_not_exist() -> None:
    session = FakeCaseSession([FakeScalarOneResult(None)])

    with pytest.raises(EntityNotFoundError):
        asyncio.run(
            create_case_from_entity(
                session,  # type: ignore[arg-type]
                uuid4(),
            )
        )

    assert session.committed is False
    assert session.objects == []


def test_build_case_list_item_exposes_root_entity_id() -> None:
    case = build_case()

    item = build_case_list_item(case)

    assert item.id == str(case.id)
    assert item.status == CaseStatus.OPEN
    assert item.risk_level == RiskLevel.HIGH
    assert item.root_entity_id == case.metadata_json["root_entity_id"]


def test_list_cases_returns_case_items() -> None:
    case = build_case()
    session = FakeCaseSession([FakeScalarManyResult([case])])

    response = asyncio.run(
        list_cases(
            session,  # type: ignore[arg-type]
        )
    )

    assert len(response) == 1
    assert response[0].id == str(case.id)
    assert response[0].title == case.title


def test_apply_case_status_update_keeps_history() -> None:
    case = build_case()
    payload = CaseStatusUpdate(status=CaseStatus.IN_REVIEW, reason="Analista asignado.")

    old_status, new_status = apply_case_status_update(case, payload)

    assert old_status == CaseStatus.OPEN.value
    assert new_status == CaseStatus.IN_REVIEW
    assert case.status == CaseStatus.IN_REVIEW.value
    assert case.metadata_json["status_history"] == [
        {
            "from": "open",
            "to": "in_review",
            "reason": "Analista asignado.",
        }
    ]


def test_update_case_status_writes_audit_log_and_commits() -> None:
    actor_user_id = uuid4()
    case = build_case()
    session = FakeCaseSession([FakeScalarOneResult(case)])
    payload = CaseStatusUpdate(status=CaseStatus.RESOLVED, reason="Caso validado y cerrado.")

    updated_case = asyncio.run(
        update_case_status(
            session,  # type: ignore[arg-type]
            case.id,
            payload,
            actor_user_id=actor_user_id,
        )
    )

    assert updated_case is case
    assert session.committed is True
    assert session.refreshed is case
    assert len(session.objects) == 1
    audit_log = session.objects[0]
    assert audit_log.actor_user_id == actor_user_id
    assert audit_log.action == "case.status_changed"
    assert audit_log.target_type == "case"
    assert audit_log.target_id == str(case.id)
    assert audit_log.metadata_json["old_status"] == "open"
    assert audit_log.metadata_json["new_status"] == "resolved"


def test_update_case_status_raises_when_case_does_not_exist() -> None:
    session = FakeCaseSession([FakeScalarOneResult(None)])

    with pytest.raises(CaseNotFoundError):
        asyncio.run(
            update_case_status(
                session,  # type: ignore[arg-type]
                uuid4(),
                CaseStatusUpdate(status=CaseStatus.ARCHIVED, reason="Archivado por duplicado."),
            )
        )

    assert session.committed is False
    assert session.objects == []


def test_apply_case_snapshot_updates_metadata_and_risk_level() -> None:
    case = build_case()
    snapshot = {
        "reports_count": 3,
        "evidence_count": 2,
        "graph_nodes_count": 4,
        "graph_edges_count": 5,
        "graph_degree": 6,
        "risk_level": "critical",
        "risk_score": 95,
    }

    apply_case_snapshot(case, snapshot)

    assert case.risk_level == "critical"
    assert case.metadata_json["snapshot"]["reports_count"] == 3
    assert case.metadata_json["snapshot"]["risk_score"] == 95
    assert case.metadata_json["snapshot"]["case_score"] == 65
    assert case.metadata_json["snapshot"]["case_risk_level"] == "critical"
    assert case.metadata_json["snapshot"]["case_scoring_rules_version"] == "case-v1"
    assert {signal["code"] for signal in case.metadata_json["snapshot"]["case_scoring_signals"]} == {
        "root_entity_risk",
        "multiple_reports",
        "evidence_present",
        "multiple_relations",
        "connected_graph",
        "entity_context",
    }


def test_build_case_snapshot_counts_context() -> None:
    entity = build_entity()
    case = build_case(entity)
    report = type(
        "ReportLike",
        (),
        {
            "id": uuid4(),
            "status": "pending",
            "reason": "Promete ganancia garantizada.",
            "source": "public_form",
            "created_at": datetime(2026, 5, 27, tzinfo=timezone.utc),
        },
    )()
    risk_score = build_risk_score(entity)
    relation = type(
        "RelationLike",
        (),
        {
            "id": uuid4(),
            "source_entity_id": entity.id,
            "target_entity_id": uuid4(),
            "relation_type": "mentioned_in_report",
            "evidence": {},
        },
    )()
    target = build_entity()
    target.id = relation.target_entity_id
    session = FakeCaseSession(
        [
            FakeScalarManyResult([report]),
            FakeScalarOneResult(2),
            FakeScalarManyResult([(relation, entity, target)]),
            FakeScalarOneResult(1),
            FakeScalarOneResult(1),
            FakeScalarOneResult(risk_score),
            FakeScalarOneResult(3),
            FakeScalarOneResult(4),
        ]
    )

    snapshot = asyncio.run(
        build_case_snapshot(
            session,  # type: ignore[arg-type]
            case,
        )
    )

    assert snapshot["root_entity_id"] == str(entity.id)
    assert snapshot["reports_count"] == 3
    assert snapshot["evidence_count"] == 2
    assert snapshot["graph_nodes_count"] == 2
    assert snapshot["graph_edges_count"] == 1
    assert snapshot["graph_degree"] == 2
    assert snapshot["relations_count"] == 4
    assert snapshot["risk_level"] == "high"
    assert snapshot["risk_score"] == 77


def test_sync_case_snapshot_writes_audit_log_and_commits() -> None:
    actor_user_id = uuid4()
    entity = build_entity()
    case = build_case(entity)
    risk_score = build_risk_score(entity)
    session = FakeCaseSession(
        [
            FakeScalarOneResult(case),
            FakeScalarManyResult([]),
            FakeScalarManyResult([]),
            FakeScalarOneResult(0),
            FakeScalarOneResult(0),
            FakeScalarOneResult(risk_score),
            FakeScalarOneResult(1),
            FakeScalarOneResult(0),
        ]
    )

    synced_case = asyncio.run(
        sync_case_snapshot(
            session,  # type: ignore[arg-type]
            case.id,
            actor_user_id=actor_user_id,
        )
    )

    assert synced_case is case
    assert session.committed is True
    assert session.refreshed is case
    assert case.metadata_json["snapshot"]["reports_count"] == 1
    assert case.metadata_json["snapshot"]["risk_score"] == 77
    assert case.metadata_json["snapshot"]["case_score"] == 40
    assert case.metadata_json["snapshot"]["case_risk_level"] == "critical"
    assert len(session.objects) == 3
    notification = session.objects[0]
    delivery = session.objects[1]
    audit_log = session.objects[2]
    assert isinstance(notification, Notification)
    assert notification.event_type == "case.critical"
    assert notification.severity == "critical"
    assert notification.metadata_json["case_id"] == str(case.id)
    assert notification.metadata_json["case_score"] == 40
    assert isinstance(delivery, NotificationDelivery)
    assert delivery.notification_id == notification.id
    assert delivery.channel == "webhook"
    assert delivery.status == "pending"
    assert audit_log.actor_user_id == actor_user_id
    assert audit_log.action == "case.synced"
    assert audit_log.target_type == "case"
    assert audit_log.target_id == str(case.id)
    assert audit_log.metadata_json["snapshot"]["risk_score"] == 77
    assert audit_log.metadata_json["snapshot"]["case_score"] == 40


def test_build_case_detail_includes_context() -> None:
    entity = build_entity()
    case = build_case(entity)
    report = type(
        "ReportLike",
        (),
        {
            "id": uuid4(),
            "status": "pending",
            "reason": "Promete ganancia garantizada.",
            "source": "public_form",
            "created_at": datetime(2026, 5, 27, tzinfo=timezone.utc),
        },
    )()
    report_item = build_case_report_item(report)
    graph = GraphResponse(nodes=[], edges=[])
    graph_metrics = GraphMetrics(entity_id=str(entity.id), degree=0, incoming=0, outgoing=0)

    detail = build_case_detail(
        case,
        root_entity=entity,
        reports=[report_item],
        evidence_count=2,
        graph=graph,
        graph_metrics=graph_metrics,
    )

    assert detail.id == str(case.id)
    assert detail.root_entity.id == str(entity.id)
    assert detail.reports == [report_item]
    assert detail.evidence_count == 2
    assert detail.graph == graph
    assert detail.graph_metrics == graph_metrics
    assert get_case_root_entity_id(case) == entity.id
