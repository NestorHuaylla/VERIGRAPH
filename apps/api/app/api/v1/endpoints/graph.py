from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_admin, require_report_reviewer
from app.db.session import get_db
from app.models.user import User
from app.schemas.graph import (
    GraphCommunitiesResponse,
    GraphMetrics,
    GraphProjectionResponse,
    GraphResponse,
    GraphScoresResponse,
    Neo4jSyncResponse,
)
from app.services.graph_analytics import (
    calculate_degree_centrality,
    calculate_pagerank,
    detect_louvain_communities,
    ensure_gds_projection,
)
from app.services.graph_engine import build_entity_graph, build_graph_preview, calculate_entity_graph_metrics
from app.services.neo4j_sync import Neo4jGraphStore, sync_postgres_graph_to_neo4j

router = APIRouter()


@router.get("/preview", response_model=GraphResponse)
async def graph_preview(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    return await build_graph_preview(db, limit=limit)


@router.get("/entity/{entity_id}", response_model=GraphResponse)
async def graph_for_entity(
    entity_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    return await build_entity_graph(db, entity_id=entity_id, limit=limit)


@router.get("/entity/{entity_id}/metrics", response_model=GraphMetrics)
async def graph_metrics_for_entity(
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> GraphMetrics:
    return await calculate_entity_graph_metrics(db, entity_id=entity_id)


@router.post("/sync/neo4j", response_model=Neo4jSyncResponse)
async def sync_graph_to_neo4j(
    batch_size: int = Query(default=500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> Neo4jSyncResponse:
    store = Neo4jGraphStore.from_settings(settings)
    try:
        result = await sync_postgres_graph_to_neo4j(db, store, batch_size=batch_size)
    finally:
        await store.close()

    return Neo4jSyncResponse(
        entities_synced=result.entities_synced,
        relations_synced=result.relations_synced,
        constraints_ensured=result.constraints_ensured,
    )


@router.post("/analytics/projection", response_model=GraphProjectionResponse)
async def create_or_refresh_gds_projection(
    refresh: bool = Query(default=False),
    _: User = Depends(require_report_reviewer),
) -> GraphProjectionResponse:
    store = Neo4jGraphStore.from_settings(settings)
    try:
        projection = await ensure_gds_projection(store, refresh=refresh)
    finally:
        await store.close()

    return GraphProjectionResponse(
        graph_name=projection.graph_name,
        node_count=projection.node_count,
        relationship_count=projection.relationship_count,
        created=projection.created,
    )


@router.get("/analytics/pagerank", response_model=GraphScoresResponse)
async def graph_pagerank(
    limit: int = Query(default=25, ge=1, le=100),
    refresh_projection: bool = Query(default=False),
    _: User = Depends(require_report_reviewer),
) -> GraphScoresResponse:
    store = Neo4jGraphStore.from_settings(settings)
    try:
        scores = await calculate_pagerank(store, limit=limit, refresh_projection=refresh_projection)
    finally:
        await store.close()

    return GraphScoresResponse(items=scores)


@router.get("/analytics/degree", response_model=GraphScoresResponse)
async def graph_degree_centrality(
    limit: int = Query(default=25, ge=1, le=100),
    refresh_projection: bool = Query(default=False),
    _: User = Depends(require_report_reviewer),
) -> GraphScoresResponse:
    store = Neo4jGraphStore.from_settings(settings)
    try:
        scores = await calculate_degree_centrality(store, limit=limit, refresh_projection=refresh_projection)
    finally:
        await store.close()

    return GraphScoresResponse(items=scores)


@router.get("/analytics/communities", response_model=GraphCommunitiesResponse)
async def graph_louvain_communities(
    limit: int = Query(default=10, ge=1, le=50),
    refresh_projection: bool = Query(default=False),
    _: User = Depends(require_report_reviewer),
) -> GraphCommunitiesResponse:
    store = Neo4jGraphStore.from_settings(settings)
    try:
        communities = await detect_louvain_communities(store, limit=limit, refresh_projection=refresh_projection)
    finally:
        await store.close()

    return GraphCommunitiesResponse(communities=communities)
