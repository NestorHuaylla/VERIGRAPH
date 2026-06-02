from app.core.constants import RiskLevel
from app.services.case_scoring import CASE_SCORING_RULES_VERSION, calculate_case_score


def test_calculate_case_score_uses_root_risk_and_context() -> None:
    result = calculate_case_score(
        {
            "risk_score": 30,
            "reports_count": 3,
            "evidence_count": 2,
            "relations_count": 4,
            "graph_degree": 5,
            "graph_nodes_count": 6,
        }
    )

    assert result.score == 55
    assert result.level == RiskLevel.CRITICAL
    assert result.rules_version == CASE_SCORING_RULES_VERSION
    assert {signal.code for signal in result.signals} == {
        "root_entity_risk",
        "multiple_reports",
        "evidence_present",
        "multiple_relations",
        "connected_graph",
        "entity_context",
    }


def test_calculate_case_score_caps_root_risk_weight() -> None:
    result = calculate_case_score(
        {
            "risk_score": 95,
            "reports_count": 1,
            "evidence_count": 0,
            "relations_count": 0,
            "graph_degree": 0,
            "graph_nodes_count": 0,
        }
    )

    assert result.score == 40
    assert result.level == RiskLevel.CRITICAL
    assert [signal.code for signal in result.signals] == ["root_entity_risk"]
    assert result.signals[0].weight == 40


def test_calculate_case_score_returns_low_without_signals() -> None:
    result = calculate_case_score({})

    assert result.score == 0
    assert result.level == RiskLevel.LOW
    assert result.signals == []
    assert "falta de senales" in result.explanation
