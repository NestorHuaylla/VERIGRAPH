import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.constants import UserRole
from app.core.dependencies import require_roles
from app.core.security import create_access_token, decode_access_token, hash_password
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.services.auth import (
    DuplicateUserError,
    InvalidCredentialsError,
    authenticate_user,
    build_token_response,
    register_user,
)


class FakeScalarOneResult:
    def __init__(self, item: object | None) -> None:
        self.item = item

    def scalar_one_or_none(self) -> object | None:
        return self.item


class FakeAuthSession:
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
        self.refreshed = obj


def build_user(*, role: UserRole = UserRole.REPORTER, is_active: bool = True) -> User:
    user = User(
        email="demo@example.com",
        password_hash=hash_password("correct-password"),
        role=role.value,
        is_active=is_active,
    )
    user.id = uuid4()
    user.created_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    user.updated_at = datetime(2026, 5, 27, tzinfo=timezone.utc)
    return user


def test_register_user_creates_reporter_and_commits() -> None:
    session = FakeAuthSession([FakeScalarOneResult(None)])
    payload = RegisterRequest(email="Demo@Example.com", password="correct-password")

    user = asyncio.run(
        register_user(
            session,  # type: ignore[arg-type]
            payload,
        )
    )

    assert session.committed is True
    assert session.refreshed is user
    assert session.objects == [user]
    assert user.email == "demo@example.com"
    assert user.role == UserRole.REPORTER.value
    assert user.is_active is True
    assert user.password_hash != "correct-password"


def test_register_user_rejects_duplicate_email() -> None:
    session = FakeAuthSession([FakeScalarOneResult(build_user())])
    payload = RegisterRequest(email="demo@example.com", password="correct-password")

    with pytest.raises(DuplicateUserError):
        asyncio.run(
            register_user(
                session,  # type: ignore[arg-type]
                payload,
            )
        )

    assert session.committed is False
    assert session.objects == []


def test_authenticate_user_accepts_valid_password() -> None:
    user = build_user(role=UserRole.ADMIN)
    session = FakeAuthSession([FakeScalarOneResult(user)])

    authenticated = asyncio.run(
        authenticate_user(
            session,  # type: ignore[arg-type]
            "demo@example.com",
            "correct-password",
        )
    )

    assert authenticated is user


def test_authenticate_user_rejects_invalid_password() -> None:
    session = FakeAuthSession([FakeScalarOneResult(build_user())])

    with pytest.raises(InvalidCredentialsError):
        asyncio.run(
            authenticate_user(
                session,  # type: ignore[arg-type]
                "demo@example.com",
                "wrong-password",
            )
        )


def test_build_token_response_contains_user_and_decodable_token() -> None:
    user = build_user(role=UserRole.ANALYST)

    response = build_token_response(user)
    payload = decode_access_token(response.access_token)

    assert response.token_type == "bearer"
    assert response.user.id == str(user.id)
    assert response.user.role == UserRole.ANALYST
    assert payload is not None
    assert payload["sub"] == str(user.id)
    assert payload["roles"] == ["analyst"]


def test_decode_access_token_returns_none_for_invalid_token() -> None:
    assert decode_access_token("not-a-real-token") is None


def test_require_roles_allows_matching_role() -> None:
    user = build_user(role=UserRole.LEGAL)
    dependency = require_roles(UserRole.ADMIN, UserRole.LEGAL)

    allowed_user = asyncio.run(dependency(user))

    assert allowed_user is user


def test_require_roles_rejects_non_matching_role() -> None:
    user = build_user(role=UserRole.REPORTER)
    dependency = require_roles(UserRole.ADMIN, UserRole.LEGAL)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(dependency(user))

    assert exc_info.value.status_code == 403


def test_create_access_token_can_be_decoded() -> None:
    user_id = uuid4()

    token = create_access_token(subject=str(user_id), roles=[UserRole.ADMIN.value])
    payload = decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == str(user_id)
    assert payload["roles"] == ["admin"]
