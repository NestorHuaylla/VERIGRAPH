from uuid import uuid4

from app.models.entity import Entity, EntityRelation
from app.services.graph_engine import build_graph_edge, build_graph_from_relation_rows, build_graph_metrics, build_graph_node


def make_entity(entity_type: str, display_value: str) -> Entity:
    entity = Entity(
        type=entity_type,
        raw_value=display_value,
        normalized_value=display_value,
        display_value=display_value,
        metadata_json={},
    )
    entity.id = uuid4()
    return entity


def make_relation(source: Entity, target: Entity) -> EntityRelation:
    relation = EntityRelation(
        source_entity_id=source.id,
        target_entity_id=target.id,
        relation_type="mentioned_in_report",
        evidence={"report_id": "report-1"},
    )
    relation.id = uuid4()
    return relation


def test_build_graph_node_from_entity() -> None:
    entity = make_entity("phone", "+51999999999")

    node = build_graph_node(entity)

    assert node.id == str(entity.id)
    assert node.label == "+51999999999"
    assert node.type == "phone"


def test_build_graph_edge_from_relation() -> None:
    source = make_entity("url", "https://estafa-peru.com/oferta")
    target = make_entity("phone", "+51999999999")
    relation = make_relation(source, target)

    edge = build_graph_edge(relation)

    assert edge.id == str(relation.id)
    assert edge.source == str(source.id)
    assert edge.target == str(target.id)
    assert edge.type == "mentioned_in_report"
    assert edge.evidence == {"report_id": "report-1"}


def test_build_graph_from_relation_rows_deduplicates_nodes() -> None:
    source = make_entity("url", "https://estafa-peru.com/oferta")
    phone = make_entity("phone", "+51999999999")
    wallet = make_entity("wallet", "evm:0xabcdef1234567890abcdef1234567890abcdef12")
    phone_relation = make_relation(source, phone)
    wallet_relation = make_relation(source, wallet)

    graph = build_graph_from_relation_rows(
        [
            (phone_relation, source, phone),
            (wallet_relation, source, wallet),
        ]
    )

    assert len(graph.nodes) == 3
    assert len(graph.edges) == 2
    assert {node.id for node in graph.nodes} == {str(source.id), str(phone.id), str(wallet.id)}


def test_build_graph_metrics_calculates_degree() -> None:
    entity_id = uuid4()

    metrics = build_graph_metrics(entity_id=entity_id, incoming=5, outgoing=3)

    assert metrics.entity_id == str(entity_id)
    assert metrics.incoming == 5
    assert metrics.outgoing == 3
    assert metrics.degree == 8
