from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserActiveUpdate, UserListItem, UserRoleUpdate, UserUpdateResponse
from app.services.users import UserNotFoundError
from app.services.users import list_users as list_users_service
from app.services.users import update_user_active as update_user_active_service
from app.services.users import update_user_role as update_user_role_service

router = APIRouter()


@router.get("", response_model=list[UserListItem])
async def list_users(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[UserListItem]:
    return await list_users_service(db, limit=limit, offset=offset)


@router.patch("/{user_id}/role", response_model=UserUpdateResponse)
async def update_user_role(
    user_id: UUID,
    payload: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserUpdateResponse:
    try:
        return await update_user_role_service(db, user_id, payload, actor_user_id=current_user.id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.") from exc


@router.patch("/{user_id}/active", response_model=UserUpdateResponse)
async def update_user_active(
    user_id: UUID,
    payload: UserActiveUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserUpdateResponse:
    try:
        return await update_user_active_service(db, user_id, payload, actor_user_id=current_user.id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.") from exc
