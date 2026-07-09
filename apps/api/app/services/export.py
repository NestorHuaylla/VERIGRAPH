import csv
import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.report import ReportDetailResponse, ReportListItem

CSV_COLUMNS = [
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


def export_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def reports_csv_filename() -> str:
    return f"verigraph-reportes-{export_timestamp()}.csv"


def report_pdf_filename(report_id: str) -> str:
    return f"verigraph-reporte-{report_id}.pdf"


def build_reports_csv(reports: list[ReportListItem]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()

    for report in reports:
        row = report.model_dump()
        row["entity_type"] = row["entity_type"].value if row.get("entity_type") else ""
        row["risk_level"] = row["risk_level"].value if row.get("risk_level") else ""
        row["created_at"] = row["created_at"].isoformat() if row.get("created_at") else ""
        writer.writerow(row)

    return buffer.getvalue()


def build_report_detail_pdf(report: ReportDetailResponse) -> bytes:
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"VeriGraph - Reporte {report.id}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "VeriGraphTitle", parent=styles["Heading1"], fontSize=18, spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        "VeriGraphSubtitle", parent=styles["Normal"], fontSize=9, textColor=colors.grey
    )
    section_style = ParagraphStyle(
        "VeriGraphSection", parent=styles["Heading2"], fontSize=12, spaceBefore=14, spaceAfter=6
    )
    body_style = styles["BodyText"]

    story = [
        Paragraph("VeriGraph &mdash; Reporte de entidad", title_style),
        Paragraph(f"ID de reporte: {report.id}", subtitle_style),
        Paragraph(
            f"Generado el {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            subtitle_style,
        ),
        Spacer(1, 0.6 * cm),
    ]

    summary_rows = [
        ["Estado", report.status.value],
        ["Fuente", report.source],
        ["Entidad", report.entity_value or "-"],
        ["Tipo de entidad", report.entity_type.value if report.entity_type else "-"],
        ["Valor normalizado", report.entity_normalized_value or "-"],
        ["Contacto del reportante", report.reporter_contact or "-"],
        ["Creado", report.created_at.strftime("%Y-%m-%d %H:%M UTC")],
        ["Actualizado", report.updated_at.strftime("%Y-%m-%d %H:%M UTC") if report.updated_at else "-"],
    ]
    summary_table = Table(summary_rows, colWidths=[5 * cm, 10 * cm])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#334155")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    story.append(summary_table)

    story.append(Paragraph("Motivo del reporte", section_style))
    story.append(Paragraph(escape_for_pdf(report.reason), body_style))

    story.append(Paragraph("Analisis de riesgo", section_style))
    if report.risk_score is not None:
        story.append(
            Paragraph(
                f"Score: <b>{report.risk_score}</b> &mdash; Nivel: "
                f"<b>{report.risk_level.value if report.risk_level else '-'}</b>",
                body_style,
            )
        )
        if report.risk_explanation:
            story.append(Spacer(1, 0.2 * cm))
            story.append(Paragraph(escape_for_pdf(report.risk_explanation), body_style))

        if report.risk_signals:
            story.append(Spacer(1, 0.3 * cm))
            signal_rows = [["Codigo", "Descripcion", "Peso"]]
            signal_rows += [[s.code, s.label, str(s.weight)] for s in report.risk_signals]
            signal_table = Table(signal_rows, colWidths=[3.5 * cm, 9 * cm, 2.5 * cm])
            signal_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(signal_table)
    else:
        story.append(Paragraph("Sin score de riesgo calculado.", body_style))

    document.build(story)
    return buffer.getvalue()


def escape_for_pdf(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
