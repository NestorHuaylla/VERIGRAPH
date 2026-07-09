import csv
import io
from datetime import datetime, timezone

from app.core.constants import EntityType, ReviewStatus, RiskLevel
from app.schemas.report import ReportDetailResponse, ReportListItem
from app.schemas.risk import RiskSignal
from app.services.export import (
    build_report_detail_pdf,
    build_reports_csv,
    report_pdf_filename,
    reports_csv_filename,
)


def build_list_item(**overrides: object) -> ReportListItem:
    defaults: dict[str, object] = {
        "id": "11111111-1111-1111-1111-111111111111",
        "entity_id": "22222222-2222-2222-2222-222222222222",
        "entity_type": EntityType.URL,
        "entity_value": "https://sitio-sospechoso.com/oferta",
        "entity_normalized_value": "sitio-sospechoso.com/oferta",
        "status": ReviewStatus.PENDING.value,
        "risk_score": 72,
        "risk_level": RiskLevel.HIGH,
        "created_at": datetime(2026, 7, 1, 10, 30, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return ReportListItem(**defaults)


def build_detail(**overrides: object) -> ReportDetailResponse:
    defaults: dict[str, object] = {
        "id": "11111111-1111-1111-1111-111111111111",
        "entity_id": "22222222-2222-2222-2222-222222222222",
        "entity_type": EntityType.URL,
        "entity_value": "https://sitio-sospechoso.com/oferta",
        "entity_raw_value": "https://sitio-sospechoso.com/oferta",
        "entity_normalized_value": "sitio-sospechoso.com/oferta",
        "reporter_contact": "reportante@example.com",
        "reason": "Pide pago por adelantado y no entrega el producto.",
        "status": ReviewStatus.SUSPECT,
        "source": "public_form",
        "risk_score": 72,
        "risk_level": RiskLevel.HIGH,
        "risk_explanation": "Coincide con patrones de phishing conocidos.",
        "risk_signals": [RiskSignal(code="phishing_pattern", label="Patron de phishing", weight=40)],
        "risk_rules_version": "v1",
        "metadata": {},
        "created_at": datetime(2026, 7, 1, 10, 30, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return ReportDetailResponse(**defaults)


def test_build_reports_csv_includes_header_and_rows() -> None:
    reports = [build_list_item(), build_list_item(id="33333333-3333-3333-3333-333333333333", risk_score=None, risk_level=None)]

    csv_content = build_reports_csv(reports)
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = list(reader)

    assert reader.fieldnames == [
        "id",
        "entity_id",
        "entity_type",
        "entity_value",
        "entity_normalized_value",
        "status",
        "risk_score",
        "risk_level",
        "created_at",
    ]
    assert len(rows) == 2
    assert rows[0]["entity_type"] == "url"
    assert rows[0]["risk_level"] == "high"
    assert rows[0]["created_at"] == "2026-07-01T10:30:00+00:00"
    assert rows[1]["risk_score"] == ""
    assert rows[1]["risk_level"] == ""


def test_build_reports_csv_handles_missing_entity() -> None:
    reports = [
        build_list_item(
            entity_id=None,
            entity_type=None,
            entity_value=None,
            entity_normalized_value=None,
        )
    ]

    csv_content = build_reports_csv(reports)
    rows = list(csv.DictReader(io.StringIO(csv_content)))

    assert rows[0]["entity_type"] == ""
    assert rows[0]["entity_value"] == ""


def test_build_report_detail_pdf_returns_valid_pdf_bytes() -> None:
    detail = build_detail()

    pdf_bytes = build_report_detail_pdf(detail)

    assert pdf_bytes.startswith(b"%PDF")
    assert b"%%EOF" in pdf_bytes


def test_build_report_detail_pdf_without_risk_score() -> None:
    detail = build_detail(risk_score=None, risk_level=None, risk_explanation=None, risk_signals=[])

    pdf_bytes = build_report_detail_pdf(detail)

    assert pdf_bytes.startswith(b"%PDF")


def test_reports_csv_filename_has_csv_extension() -> None:
    assert reports_csv_filename().endswith(".csv")
    assert reports_csv_filename().startswith("verigraph-reportes-")


def test_report_pdf_filename_includes_report_id() -> None:
    filename = report_pdf_filename("abc-123")
    assert filename == "verigraph-reporte-abc-123.pdf"
