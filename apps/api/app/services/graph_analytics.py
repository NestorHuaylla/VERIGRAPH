from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.neo4j_sync import Neo4jReadWriteClient


DEFAULT_GDS_GRAPH_NAME = "verigraph-entities"

GDS_GRAPH_EXISTS = """
CALL gds.graph.exists($graph_name)
YIELD exists
RETURN exists
"""

GDS_DROP_GRAPH = """
CALL gds.graph.drop($graph_name, false)
YIELD graphName
RETURN graphName
"""

GDS_PROJECT_GRAPH = """
CALL gds.graph.project(
    $graph_name,
    'VerigraphEntity',
    {
        VERIGRAPH_RELATION: {
            orientation: 'NATURAL'
        }
    }
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount
"""

GDS_PAGERANK = """
CALL gds.pageRank.stream($graph_name)
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS entity, score
RETURN entity.id AS entity_id,
       entity.display_value AS label,
       entity.type AS type,
       score AS score
ORDER BY score DESC
LIMIT $limit
"""

GDS_DEGREE = """
CALL gds.degree.stream($graph_name)
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS entity, score
RETURN entity.id AS entity_id,
       entity.display_value AS label,
       entity.type AS type,
       score AS score
ORDER BY score DESC
LIMIT $limit
"""

GDS_LOUVAIN = """
CALL gds.louvain.stream($graph_name)
YIELD nodeId, communityId
WITH communityId, gds.util.asNode(nodeId) AS entity
WITH communityId,
     collect({
        entity_id: entity.id,
        label: entity.display_value,
        type: entity.type
     }) AS members
RETURN communityId AS community_id,
       size(members) AS size,
       members AS members
ORDER BY size DESC
LIMIT $limit
"""

@dataclass(frozen=True)
class GraphProjection:
    graph_name: str
    node_count: int
    relationship_count: int
    created: bool


@dataclass(frozen=True)
class EntityScore:
    entity_id: str
    label: str
    type: str
    score: float


@dataclass(frozen=True)
class CommunityMember:
    entity_id: str
    label: str
    type: str


@dataclass(frozen=True)
class GraphCommunity:
    community_id: int
    size: int
    members: list[CommunityMember]


async def ensure_gds_projection(
    client: Neo4jReadWriteClient,
    *,
    graph_name: str = DEFAULT_GDS_GRAPH_NAME,
    refresh: bool = False,
) -> GraphProjection:
    if refresh:
        await client.run_write(GDS_DROP_GRAPH, graph_name=graph_name)
    elif await gds_projection_exists(client, graph_name=graph_name):
        return GraphProjection(
            graph_name=graph_name,
            node_count=0,
            relationship_count=0,
            created=False,
        )

    rows = await client.run_read(GDS_PROJECT_GRAPH, graph_name=graph_name)
    row = rows[0] if rows else {}
    return GraphProjection(
        graph_name=str(row.get("graphName") or graph_name),
        node_count=int(row.get("nodeCount") or 0),
        relationship_count=int(row.get("relationshipCount") or 0),
        created=True,
    )


async def gds_projection_exists(
    client: Neo4jReadWriteClient,
    *,
    graph_name: str = DEFAULT_GDS_GRAPH_NAME,
) -> bool:
    rows = await client.run_read(GDS_GRAPH_EXISTS, graph_name=graph_name)
    if not rows:
        return False
    return bool(rows[0].get("exists"))


async def calculate_pagerank(
    client: Neo4jReadWriteClient,
    *,
    limit: int = 25,
    graph_name: str = DEFAULT_GDS_GRAPH_NAME,
    refresh_projection: bool = False,
) -> list[EntityScore]:
    await ensure_gds_projection(client, graph_name=graph_name, refresh=refresh_projection)
    rows = await client.run_read(GDS_PAGERANK, graph_name=graph_name, limit=limit)
    return [build_entity_score(row) for row in rows]


async def calculate_degree_centrality(
    client: Neo4jReadWriteClient,
    *,
    limit: int = 25,
    graph_name: str = DEFAULT_GDS_GRAPH_NAME,
    refresh_projection: bool = False,
) -> list[EntityScore]:
    await ensure_gds_projection(client, graph_name=graph_name, refresh=refresh_projection)
    rows = await client.run_read(GDS_DEGREE, graph_name=graph_name, limit=limit)
    return [build_entity_score(row) for row in rows]


async def detect_louvain_communities(
    client: Neo4jReadWriteClient,
    *,
    limit: int = 10,
    graph_name: str = DEFAULT_GDS_GRAPH_NAME,
    refresh_projection: bool = False,
) -> list[GraphCommunity]:
    await ensure_gds_projection(client, graph_name=graph_name, refresh=refresh_projection)
    rows = await client.run_read(GDS_LOUVAIN, graph_name=graph_name, limit=limit)
    return [build_graph_community(row) for row in rows]


def build_entity_score(row: dict[str, Any]) -> EntityScore:
    return EntityScore(
        entity_id=str(row.get("entity_id") or ""),
        label=str(row.get("label") or ""),
        type=str(row.get("type") or ""),
        score=float(row.get("score") or 0),
    )


def build_graph_community(row: dict[str, Any]) -> GraphCommunity:
    return GraphCommunity(
        community_id=int(row.get("community_id") or 0),
        size=int(row.get("size") or 0),
        members=[build_community_member(member) for member in row.get("members", [])],
    )


def build_community_member(row: dict[str, Any]) -> CommunityMember:
    return CommunityMember(
        entity_id=str(row.get("entity_id") or ""),
        label=str(row.get("label") or ""),
        type=str(row.get("type") or ""),
    )
