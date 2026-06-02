from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserActiveUpdate, UserListItem, UserRoleUpdate, UserUpdateResponse
from app.services.audit import write_audit_log


MIN_PASSWORD_LENGTH = 8
DEFAULT_USER_LIMIT = 100


class UserAlreadyExistsError(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(f"User {email} already exists.")
        self.email = email


class InvalidPasswordError(Exception):
    def __init__(self) -> None:
        super().__init__(f"Password must contain at least {MIN_PASSWORD_LENGTH} characters.")


class UserNotFoundError(Exception):
    def __init__(self, user_id: UUID) -> None:
        super().__init__(f"User {user_id} was not found.")
        self.user_id = user_id


async def list_users(
    db: AsyncSession,
    *,
    limit: int = DEFAULT_USER_LIMIT,
    offset: int = 0,
) -> list[UserListItem]:
    result = await db.execute(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset))
    return [build_user_list_item(user) for user in result.scalars().all()]


async def create_user_with_role(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    role: UserRole,
    is_active: bool = True,
) -> User:
    normalized_email = normalize_email(email)
    validate_password(password)

    existing_user = await find_user_by_email(db, normalized_email)
    if existing_user is not None:
        raise UserAlreadyExistsError(normalized_email)

    user = build_user_with_role(
        email=normalized_email,
        password=password,
        role=role,
        is_active=is_active,
    )
    db.add(user)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise UserAlreadyExistsError(normalized_email) from exc

    await db.refresh(user)
    return user


async def create_admin_user(db: AsyncSession, *, email: str, password: str) -> User:
    return await create_user_with_role(
        db,
        email=email,
        password=password,
        role=UserRole.ADMIN,
    )


async def find_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == normalize_email(email)))
    return result.scalar_one_or_none()


async def find_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def find_or_create_external_user(
    db: AsyncSession,
    *,
    email: str,
    role: UserRole,
) -> User:
    normalized_email = normalize_email(email)
    user = await find_user_by_email(db, normalized_email)
    if user is not None:
        if user.role != role.value:
            user.role = role.value
            await db.commit()
            await db.refresh(user)
        return user

    user = User(
        email=normalized_email,
        password_hash=hash_password(f"external-auth:{normalized_email}"),
        role=role.value,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_role(
    db: AsyncSession,
    user_id: UUID,
    payload: UserRoleUpdate,
    *,
    actor_user_id: UUID | None = None,
) -> UserUpdateResponse:
    user = await find_user_by_id(db, user_id)
    if user is None:
        raise UserNotFoundError(user_id)

    old_role, new_role = apply_user_role_update(user, payload)
    await write_user_role_changed_audit_log(
        db,
        user,
        old_role=old_role,
        new_role=new_role,
        actor_user_id=actor_user_id,
    )

    await db.commit()
    await db.refresh(user)

    return build_user_update_response(user, message="Rol de usuario actualizado.")


async def update_user_active(
    db: AsyncSession,
    user_id: UUID,
    payload: UserActiveUpdate,
    *,
    actor_user_id: UUID | None = None,
) -> UserUpdateResponse:
    user = await find_user_by_id(db, user_id)
    if user is None:
        raise UserNotFoundError(user_id)

    old_active, new_active = apply_user_active_update(user, payload)
    await write_user_active_changed_audit_log(
        db,
        user,
        old_active=old_active,
        new_active=new_active,
        actor_user_id=actor_user_id,
    )

    await db.commit()
    await db.refresh(user)

    return build_user_update_response(user, message="Estado activo de usuario actualizado.")


def build_user_with_role(
    *,
    email: str,
    password: str,
    role: UserRole,
    is_active: bool = True,
) -> User:
    return User(
        email=normalize_email(email),
        password_hash=hash_password(password),
        role=role.value,
        is_active=is_active,
    )


def build_user_list_item(user: User) -> UserListItem:
    return UserListItem(
        id=str(user.id),
        email=user.email,
        role=UserRole(user.role),
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def build_user_update_response(user: User, *, message: str) -> UserUpdateResponse:
    return UserUpdateResponse(
        id=str(user.id),
        email=user.email,
        role=UserRole(user.role),
        is_active=user.is_active,
        message=message,
    )


def apply_user_role_update(user: User, payload: UserRoleUpdate) -> tuple[str, UserRole]:
    old_role = user.role
    user.role = payload.role.value
    return old_role, payload.role


def apply_user_active_update(user: User, payload: UserActiveUpdate) -> tuple[bool, bool]:
    old_active = user.is_active
    user.is_active = payload.is_active
    return old_active, payload.is_active


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidPasswordError()


async def write_user_role_changed_audit_log(
    db: AsyncSession,
    user: User,
    *,
    old_role: str,
    new_role: UserRole,
    actor_user_id: UUID | None = None,
) -> None:
    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="user.role_changed",
        target_type="user",
        target_id=str(user.id),
        metadata={
            "email": user.email,
            "old_role": old_role,
            "new_role": new_role.value,
        },
    )


async def write_user_active_changed_audit_log(
    db: AsyncSession,
    user: User,
    *,
    old_active: bool,
    new_active: bool,
    actor_user_id: UUID | None = None,
) -> None:
    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="user.active_changed",
        target_type="user",
        target_id=str(user.id),
        metadata={
            "email": user.email,
            "old_active": old_active,
            "new_active": new_active,
        },
    )
