import asyncio
from typing import Any

from app.services.graph_analytics import (
    DEFAULT_GDS_GRAPH_NAME,
    GDS_DEGREE,
    GDS_DROP_GRAPH,
    GDS_GRAPH_EXISTS,
    GDS_LOUVAIN,
    GDS_PAGERANK,
    GDS_PROJECT_GRAPH,
    build_entity_score,
    build_graph_community,
    calculate_degree_centrality,
    calculate_pagerank,
    detect_louvain_communities,
    ensure_gds_projection,
)


class FakeNeo4jClient:
    def __init__(self, read_results: list[list[dict[str, Any]]]) -> None:
        self.read_results = read_results
        self.read_calls: list[tuple[str, dict[str, Any]]] = []
        self.write_calls: list[tuple[str, dict[str, Any]]] = []

    async def run_read(self, query: str, **parameters: Any) -> list[dict[str, Any]]:
        self.read_calls.append((query, parameters))
        return self.read_results.pop(0)

    async def run_write(self, query: str, **parameters: Any) -> None:
        self.write_calls.append((query, parameters))


def test_ensure_gds_projection_reuses_existing_projection() -> None:
    client = FakeNeo4jClient(read_results=[[{"exists": True}]])

    projection = asyncio.run(ensure_gds_projection(client))

    assert projection.graph_name == DEFAULT_GDS_GRAPH_NAME
    assert projection.node_count == 0
    assert projection.relationship_count == 0
    assert projection.created is False
    assert client.read_calls == [(GDS_GRAPH_EXISTS, {"graph_name": DEFAULT_GDS_GRAPH_NAME})]
    assert client.write_calls == []


def test_ensure_gds_projection_creates_projection_when_missing() -> None:
    client = FakeNeo4jClient(
        read_results=[
            [{"exists": False}],
            [{"graphName": DEFAULT_GDS_GRAPH_NAME, "nodeCount": 3, "relationshipCount": 2}],
        ]
    )

    projection = asyncio.run(ensure_gds_projection(client))

    assert projection.created is True
    assert projection.node_count == 3
    assert projection.relationship_count == 2
    assert client.read_calls[1] == (GDS_PROJECT_GRAPH, {"graph_name": DEFAULT_GDS_GRAPH_NAME})


def test_ensure_gds_projection_refreshes_existing_projection() -> None:
    client = FakeNeo4jClient(
        read_results=[
            [{"graphName": DEFAULT_GDS_GRAPH_NAME, "nodeCount": 5, "relationshipCount": 4}],
        ]
    )

    projection = asyncio.run(ensure_gds_projection(client, refresh=True))

    assert projection.created is True
    assert projection.node_count == 5
    assert client.write_calls == [(GDS_DROP_GRAPH, {"graph_name": DEFAULT_GDS_GRAPH_NAME})]
    assert client.read_calls == [(GDS_PROJECT_GRAPH, {"graph_name": DEFAULT_GDS_GRAPH_NAME})]


def test_build_entity_score_normalizes_row() -> None:
    score = build_entity_score(
        {
            "entity_id": "entity-1",
            "label": "https://example.test",
            "type": "url",
            "score": 0.42,
        }
    )

    assert score.entity_id == "entity-1"
    assert score.label == "https://example.test"
    assert score.type == "url"
    assert score.score == 0.42


def test_build_graph_community_normalizes_members() -> None:
    community = build_graph_community(
        {
            "community_id": 7,
            "size": 2,
            "members": [
                {"entity_id": "entity-1", "label": "a", "type": "url"},
                {"entity_id": "entity-2", "label": "b", "type": "phone"},
            ],
        }
    )

    assert community.community_id == 7
    assert community.size == 2
    assert [member.entity_id for member in community.members] == ["entity-1", "entity-2"]


def test_calculate_pagerank_ensures_projection_then_streams_scores() -> None:
    client = FakeNeo4jClient(
        read_results=[
            [{"exists": True}],
            [{"entity_id": "entity-1", "label": "https://example.test", "type": "url", "score": 1.25}],
        ]
    )

    scores = asyncio.run(calculate_pagerank(client, limit=5))

    assert len(scores) == 1
    assert scores[0].entity_id == "entity-1"
    assert client.read_calls[1] == (GDS_PAGERANK, {"graph_name": DEFAULT_GDS_GRAPH_NAME, "limit": 5})


def test_calculate_degree_centrality_streams_scores() -> None:
    client = FakeNeo4jClient(
        read_results=[
            [{"exists": True}],
            [{"entity_id": "entity-1", "label": "+51999999999", "type": "phone", "score": 3.0}],
        ]
    )

    scores = asyncio.run(calculate_degree_centrality(client, limit=10))

    assert scores[0].score == 3.0
    assert client.read_calls[1] == (GDS_DEGREE, {"graph_name": DEFAULT_GDS_GRAPH_NAME, "limit": 10})


def test_detect_louvain_communities_streams_communities() -> None:
    client = FakeNeo4jClient(
        read_results=[
            [{"exists": True}],
            [
                {
                    "community_id": 2,
                    "size": 1,
                    "members": [{"entity_id": "entity-1", "label": "wallet", "type": "wallet"}],
                }
            ],
        ]
    )

    communities = asyncio.run(detect_louvain_communities(client, limit=3))

    assert communities[0].community_id == 2
    assert communities[0].members[0].type == "wallet"
    assert client.read_calls[1] == (GDS_LOUVAIN, {"graph_name": DEFAULT_GDS_GRAPH_NAME, "limit": 3})
