import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.constants import UserRole
from app.models.user import User
from app.scripts.create_admin import parse_args
from app.schemas.user import UserActiveUpdate, UserRoleUpdate
from app.services.users import (
    InvalidPasswordError,
    UserAlreadyExistsError,
    UserNotFoundError,
    apply_user_active_update,
    apply_user_role_update,
    build_user_with_role,
    create_admin_user,
    create_user_with_role,
    list_users,
    normalize_email,
    update_user_active,
    update_user_role,
)


class FakeScalarOneResult:
    def __init__(self, item: object | None) -> None:
        self.item = item

    def scalar_one_or_none(self) -> object | None:
        return self.item


class FakeScalarManyResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def scalars(self) -> "FakeScalarManyResult":
        return self

    def all(self) -> list[object]:
        return self.items


class FakeUserSession:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.objects: list[object] = []
        self.committed = False
        self.rolled_back = False
        self.refreshed: object | None = None

    async def execute(self, statement: object) -> object:
        self.statement = statement
        return self.results.pop(0)

    def add(self, obj: object) -> None:
        self.objects.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, obj: object) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
        self.refreshed = obj


def build_existing_user() -> User:
    user = build_user_with_role(
        email="admin@verigraph.local",
        password="strong-password",
        role=UserRole.ADMIN,
    )
    user.id = uuid4()
    user.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    user.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return user


def test_normalize_email_trims_and_lowercases() -> None:
    assert normalize_email(" Admin@Verigraph.Local ") == "admin@verigraph.local"


def test_build_user_with_role_hashes_password_and_sets_role() -> None:
    user = build_user_with_role(
        email="Admin@Verigraph.Local",
        password="strong-password",
        role=UserRole.ADMIN,
    )

    assert user.email == "admin@verigraph.local"
    assert user.password_hash != "strong-password"
    assert user.role == UserRole.ADMIN.value
    assert user.is_active is True


def test_create_user_with_role_creates_admin_and_commits() -> None:
    session = FakeUserSession([FakeScalarOneResult(None)])

    user = asyncio.run(
        create_user_with_role(
            session,  # type: ignore[arg-type]
            email="Admin@Verigraph.Local",
            password="strong-password",
            role=UserRole.ADMIN,
        )
    )

    assert session.committed is True
    assert session.refreshed is user
    assert session.objects == [user]
    assert user.email == "admin@verigraph.local"
    assert user.role == UserRole.ADMIN.value


def test_create_admin_user_uses_admin_role() -> None:
    session = FakeUserSession([FakeScalarOneResult(None)])

    user = asyncio.run(
        create_admin_user(
            session,  # type: ignore[arg-type]
            email="admin@verigraph.local",
            password="strong-password",
        )
    )

    assert user.role == UserRole.ADMIN.value


def test_create_user_with_role_rejects_duplicate_email() -> None:
    session = FakeUserSession([FakeScalarOneResult(build_existing_user())])

    with pytest.raises(UserAlreadyExistsError):
        asyncio.run(
            create_user_with_role(
                session,  # type: ignore[arg-type]
                email="admin@verigraph.local",
                password="strong-password",
                role=UserRole.ADMIN,
            )
        )

    assert session.committed is False
    assert session.objects == []


def test_create_user_with_role_rejects_short_password() -> None:
    session = FakeUserSession([])

    with pytest.raises(InvalidPasswordError):
        asyncio.run(
            create_user_with_role(
                session,  # type: ignore[arg-type]
                email="admin@verigraph.local",
                password="short",
                role=UserRole.ADMIN,
            )
        )

    assert session.committed is False
    assert session.objects == []


def test_create_admin_parse_args_reads_email_and_password() -> None:
    args = parse_args(["--email", "admin@verigraph.local", "--password", "strong-password"])

    assert args.email == "admin@verigraph.local"
    assert args.password == "strong-password"


def test_list_users_returns_admin_items() -> None:
    user = build_existing_user()
    session = FakeUserSession([FakeScalarManyResult([user])])

    response = asyncio.run(
        list_users(
            session,  # type: ignore[arg-type]
        )
    )

    assert len(response) == 1
    assert response[0].id == str(user.id)
    assert response[0].email == "admin@verigraph.local"
    assert response[0].role == UserRole.ADMIN
    assert response[0].is_active is True


def test_apply_user_role_update_changes_role() -> None:
    user = build_existing_user()
    payload = UserRoleUpdate(role=UserRole.LEGAL)

    old_role, new_role = apply_user_role_update(user, payload)

    assert old_role == UserRole.ADMIN.value
    assert new_role == UserRole.LEGAL
    assert user.role == UserRole.LEGAL.value


def test_update_user_role_writes_audit_log_and_commits() -> None:
    actor_user_id = uuid4()
    user = build_existing_user()
    session = FakeUserSession([FakeScalarOneResult(user)])
    payload = UserRoleUpdate(role=UserRole.ANALYST)

    response = asyncio.run(
        update_user_role(
            session,  # type: ignore[arg-type]
            user.id,
            payload,
            actor_user_id=actor_user_id,
        )
    )

    assert session.committed is True
    assert session.refreshed is user
    assert response.role == UserRole.ANALYST
    assert response.message == "Rol de usuario actualizado."
    assert len(session.objects) == 1
    audit_log = session.objects[0]
    assert audit_log.actor_user_id == actor_user_id
    assert audit_log.action == "user.role_changed"
    assert audit_log.target_type == "user"
    assert audit_log.target_id == str(user.id)
    assert audit_log.metadata_json == {
        "email": "admin@verigraph.local",
        "old_role": "admin",
        "new_role": "analyst",
    }


def test_apply_user_active_update_changes_active_status() -> None:
    user = build_existing_user()
    payload = UserActiveUpdate(is_active=False)

    old_active, new_active = apply_user_active_update(user, payload)

    assert old_active is True
    assert new_active is False
    assert user.is_active is False


def test_update_user_active_writes_audit_log_and_commits() -> None:
    actor_user_id = uuid4()
    user = build_existing_user()
    session = FakeUserSession([FakeScalarOneResult(user)])
    payload = UserActiveUpdate(is_active=False)

    response = asyncio.run(
        update_user_active(
            session,  # type: ignore[arg-type]
            user.id,
            payload,
            actor_user_id=actor_user_id,
        )
    )

    assert session.committed is True
    assert session.refreshed is user
    assert response.is_active is False
    assert response.message == "Estado activo de usuario actualizado."
    assert len(session.objects) == 1
    audit_log = session.objects[0]
    assert audit_log.actor_user_id == actor_user_id
    assert audit_log.action == "user.active_changed"
    assert audit_log.target_type == "user"
    assert audit_log.target_id == str(user.id)
    assert audit_log.metadata_json == {
        "email": "admin@verigraph.local",
        "old_active": True,
        "new_active": False,
    }


def test_update_user_role_raises_when_user_does_not_exist() -> None:
    session = FakeUserSession([FakeScalarOneResult(None)])

    with pytest.raises(UserNotFoundError):
        asyncio.run(
            update_user_role(
                session,  # type: ignore[arg-type]
                uuid4(),
                UserRoleUpdate(role=UserRole.LEGAL),
            )
        )

    assert session.committed is False
    assert session.objects == []
