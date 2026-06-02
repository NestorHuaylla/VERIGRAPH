from dataclasses import dataclass

from app.core.constants import EntityType, RiskLevel
from app.schemas.risk import RiskSignal


@dataclass(frozen=True)
class ScoreResult:
    score: int
    level: RiskLevel
    explanation: str
    signals: list[RiskSignal]


RULES_VERSION = "v1"


def calculate_initial_score(
    text: str,
    entity_type: EntityType,
    normalized_value: str,
    *,
    graph_degree: int = 0,
    external_signals: list[RiskSignal] | None = None,
) -> ScoreResult:
    haystack = f"{text} {normalized_value}".lower()
    signals: list[RiskSignal] = []

    def add(code: str, label: str, weight: int) -> None:
        signals.append(RiskSignal(code=code, label=label, weight=weight))

    if any(term in haystack for term in ["ganancia garantizada", "duplica", "100%", "inversion segura"]):
        add("guaranteed_return", "Promesa de retorno garantizado", 5)
    if any(term in haystack for term in ["pago adelantado", "adelanto", "deposito primero"]):
        add("advance_payment", "Solicitud de pago adelantado", 5)
    if entity_type == EntityType.WALLET or any(term in haystack for term in ["wallet", "crypto", "btc", "usdt"]):
        add("crypto_payment", "Uso de wallet o crypto", 4)
    if entity_type in {EntityType.URL, EntityType.DOMAIN}:
        add("link_review", "Entidad web requiere revision tecnica", 2)
    if graph_degree >= 8:
        add("highly_connected_entity", "Entidad conectada a multiples entidades relacionadas", 8)
    elif graph_degree >= 3:
        add("graph_connected_entity", "Entidad conectada a varias entidades relacionadas", 4)
    signals.extend(external_signals or [])

    score = sum(signal.weight for signal in signals)
    level = classify_score(score)
    explanation = build_explanation(level, signals)
    return ScoreResult(score=score, level=level, explanation=explanation, signals=signals)


def classify_score(score: int) -> RiskLevel:
    if score >= 36:
        return RiskLevel.CRITICAL
    if score >= 21:
        return RiskLevel.HIGH
    if score >= 11:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def build_explanation(level: RiskLevel, signals: list[RiskSignal]) -> str:
    if not signals:
        return "No se detectaron senales suficientes. Requiere mas evidencia o revision externa."
    labels = ", ".join(signal.label for signal in signals)
    return f"Riesgo {level.value} por estas senales iniciales: {labels}."
