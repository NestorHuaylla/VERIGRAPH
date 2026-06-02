from app.core.constants import EntityType, RiskLevel
from app.schemas.risk import RiskSignal
from app.services.scoring import calculate_initial_score


def test_score_adds_graph_signal_for_connected_entity() -> None:
    score = calculate_initial_score(
        text="Reporte con varias conexiones.",
        entity_type=EntityType.PHONE,
        normalized_value="+51999999999",
        graph_degree=3,
    )

    assert score.score == 4
    assert score.level == RiskLevel.LOW
    assert [signal.code for signal in score.signals] == ["graph_connected_entity"]


def test_score_adds_highly_connected_graph_signal() -> None:
    score = calculate_initial_score(
        text="Reporte con muchas conexiones.",
        entity_type=EntityType.PHONE,
        normalized_value="+51999999999",
        graph_degree=8,
    )

    assert score.score == 8
    assert score.level == RiskLevel.LOW
    assert [signal.code for signal in score.signals] == ["highly_connected_entity"]


def test_score_combines_text_and_graph_signals() -> None:
    score = calculate_initial_score(
        text="Promete ganancia garantizada y pide deposito primero.",
        entity_type=EntityType.URL,
        normalized_value="https://estafa-peru.com/oferta",
        graph_degree=3,
    )

    assert score.score == 16
    assert score.level == RiskLevel.MEDIUM
    assert {signal.code for signal in score.signals} == {
        "guaranteed_return",
        "advance_payment",
        "link_review",
        "graph_connected_entity",
    }


def test_score_includes_external_reputation_signals() -> None:
    score = calculate_initial_score(
        text="URL reportada.",
        entity_type=EntityType.URL,
        normalized_value="https://bad.test",
        external_signals=[
            RiskSignal(
                code="external_high_confidence_match",
                label="Fuente externa marco la entidad como maliciosa.",
                weight=18,
            )
        ],
    )

    assert score.score == 20
    assert score.level == RiskLevel.MEDIUM
    assert {signal.code for signal in score.signals} == {
        "link_review",
        "external_high_confidence_match",
    }
