from dataclasses import dataclass

from app.core.constants import RiskLevel
from app.schemas.risk import RiskSignal
from app.services.scoring import classify_score


CASE_SCORING_RULES_VERSION = "case-v1"


@dataclass(frozen=True)
class CaseScoreResult:
    score: int
    level: RiskLevel
    explanation: str
    signals: list[RiskSignal]
    rules_version: str = CASE_SCORING_RULES_VERSION


def calculate_case_score(snapshot: dict) -> CaseScoreResult:
    signals: list[RiskSignal] = []

    def add(code: str, label: str, weight: int) -> None:
        signals.append(RiskSignal(code=code, label=label, weight=weight))

    root_risk_score = int(snapshot.get("risk_score") or 0)
    if root_risk_score:
        add("root_entity_risk", "Riesgo acumulado de la entidad raiz", min(root_risk_score, 40))

    reports_count = int(snapshot.get("reports_count") or 0)
    if reports_count >= 5:
        add("many_reports", "Multiples reportes asociados al expediente", 12)
    elif reports_count >= 2:
        add("multiple_reports", "Mas de un reporte asociado al expediente", 6)

    evidence_count = int(snapshot.get("evidence_count") or 0)
    if evidence_count >= 5:
        add("many_evidence_files", "Multiples evidencias asociadas al expediente", 8)
    elif evidence_count >= 1:
        add("evidence_present", "Evidencia asociada al expediente", 4)

    relations_count = int(snapshot.get("relations_count") or snapshot.get("graph_edges_count") or 0)
    if relations_count >= 10:
        add("many_relations", "Alta cantidad de relaciones entre entidades", 12)
    elif relations_count >= 3:
        add("multiple_relations", "Varias relaciones entre entidades", 6)

    graph_degree = int(snapshot.get("graph_degree") or 0)
    if graph_degree >= 8:
        add("high_graph_degree", "Entidad raiz altamente conectada", 10)
    elif graph_degree >= 3:
        add("connected_graph", "Entidad raiz conectada a varias entidades", 5)

    graph_nodes_count = int(snapshot.get("graph_nodes_count") or 0)
    if graph_nodes_count >= 10:
        add("large_entity_context", "Contexto de entidades amplio", 8)
    elif graph_nodes_count >= 4:
        add("entity_context", "Contexto de entidades relacionado", 4)

    score = min(sum(signal.weight for signal in signals), 100)
    level = classify_score(score)
    return CaseScoreResult(
        score=score,
        level=level,
        explanation=build_case_score_explanation(level, signals),
        signals=signals,
    )


def build_case_score_explanation(level: RiskLevel, signals: list[RiskSignal]) -> str:
    if not signals:
        return "Riesgo de expediente bajo por falta de senales agregadas."

    labels = ", ".join(signal.label for signal in signals)
    return f"Riesgo de expediente {level.value} por estas senales agregadas: {labels}."
