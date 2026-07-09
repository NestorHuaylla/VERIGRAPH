from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import UserRole
from app.core.security import decode_access_token, extract_email_from_token_payload, select_token_role
from app.db.session import get_db
from app.models.user import User
from app.services.users import find_or_create_external_user, find_user_by_email, find_user_by_id


# auto_error=False: si no viene header Authorization, no lanzamos 401 de
# inmediato; primero probamos la cookie httpOnly de sesion (ver get_token_from_request).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_token_from_request(
    request: Request,
    header_token: str | None = Depends(oauth2_scheme),
) -> str | None:
    if header_token:
        return header_token
    return request.cookies.get(settings.auth_cookie_name)


async def get_current_user(
    token: str | None = Depends(get_token_from_request),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await get_user_from_token(db, token)


async def get_user_from_token(db: AsyncSession, token: str) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_error

    subject = payload.get("sub")
    if not subject:
        raise credentials_error

    if payload.get("auth_provider") == "keycloak":
        return await get_current_oidc_user(db, payload, credentials_error)

    try:
        user_id = UUID(str(subject))
    except ValueError as exc:
        raise credentials_error from exc

    user = await find_user_by_id(db, user_id)
    if user is None:
        raise credentials_error
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user.")

    return user


async def get_current_oidc_user(
    db: AsyncSession,
    payload: dict,
    credentials_error: HTTPException,
) -> User:
    email = extract_email_from_token_payload(payload)
    if not email:
        raise credentials_error

    token_role = select_token_role(payload)
    user = None
    if settings.keycloak_auto_provision_users:
        user = await find_or_create_external_user(
            db,
            email=email,
            role=token_role or UserRole.REPORTER,
        )
    else:
        user = await find_user_by_email(db, email)
        if user is not None and token_role is not None and user.role != token_role.value:
            user.role = token_role.value
            await db.commit()
            await db.refresh(user)

    if user is None:
        raise credentials_error
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user.")
    return user


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def require_roles(*allowed_roles: UserRole) -> Callable[..., User]:
    allowed = {role.value for role in allowed_roles}

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
        return current_user

    return dependency


def require_worker_token_or_roles(*allowed_roles: UserRole) -> Callable[..., User | None]:
    allowed = {role.value for role in allowed_roles}

    async def dependency(
        authorization: str | None = Header(default=None),
        db: AsyncSession = Depends(get_db),
    ) -> User | None:
        token = extract_bearer_token(authorization)
        if settings.worker_api_token and token == settings.worker_api_token:
            return None
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = await get_user_from_token(db, token)
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
        return user

    return dependency


require_report_reviewer = require_roles(UserRole.ADMIN, UserRole.ANALYST, UserRole.LEGAL)
require_reporter_or_reviewer = require_roles(UserRole.REPORTER, UserRole.ANALYST, UserRole.ADMIN, UserRole.LEGAL)
require_worker_or_report_reviewer = require_worker_token_or_roles(UserRole.ADMIN, UserRole.ANALYST, UserRole.LEGAL)
require_admin = require_roles(UserRole.ADMIN)
