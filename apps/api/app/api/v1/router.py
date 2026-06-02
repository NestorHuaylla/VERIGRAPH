from fastapi import APIRouter

from app.api.v1.endpoints import appeals, auth, cases, entities, graph, health, notifications, reports, users

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(entities.router, prefix="/entities", tags=["entities"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
api_router.include_router(appeals.router, prefix="/appeals", tags=["appeals"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
