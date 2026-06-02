from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenResponse, UserResponse
from app.services.users import UserAlreadyExistsError, create_user_with_role, find_user_by_email


class AuthError(Exception):
    pass


DuplicateUserError = UserAlreadyExistsError


class InvalidCredentialsError(AuthError):
    pass


class InactiveUserError(AuthError):
    pass


async def register_user(db: AsyncSession, payload: RegisterRequest) -> User:
    return await create_user_with_role(
        db,
        email=str(payload.email),
        password=payload.password,
        role=UserRole.REPORTER,
    )


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    user = await find_user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    if not user.is_active:
        raise InactiveUserError()
    return user


def build_token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(subject=str(user.id), roles=[user.role]),
        user=build_user_response(user),
    )


def build_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        role=UserRole(user.role),
        is_active=user.is_active,
    )
