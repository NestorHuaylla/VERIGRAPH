from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import httpx
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.constants import UserRole

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
JWT_ALGORITHM = "HS256"
OIDC_ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, roles: list[str]) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "roles": roles,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    local_payload = decode_local_access_token(token)
    if local_payload is not None:
        local_payload["auth_provider"] = "local"
        return local_payload

    oidc_payload = decode_oidc_access_token(token)
    if oidc_payload is not None:
        oidc_payload["auth_provider"] = "keycloak"
        oidc_payload["roles"] = extract_oidc_roles(oidc_payload)
        return oidc_payload

    return None


def decode_local_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            issuer=settings.jwt_issuer,
        )
    except JWTError:
        return None


def decode_oidc_access_token(token: str) -> dict[str, Any] | None:
    issuer = settings.keycloak_issuer.rstrip("/")
    if not issuer:
        return None

    try:
        header = jwt.get_unverified_header(token)
        key = find_jwks_key(header)
        if key is None:
            return None
        return jwt.decode(
            token,
            key,
            algorithms=OIDC_ALLOWED_ALGORITHMS,
            issuer=issuer,
            audience=settings.keycloak_client_id or None,
            options={"verify_aud": bool(settings.keycloak_client_id)},
        )
    except (JWTError, httpx.HTTPError, ValueError):
        return None


def find_jwks_key(header: dict[str, Any]) -> dict[str, Any] | None:
    kid = header.get("kid")
    jwks = get_oidc_jwks()
    for key in jwks.get("keys", []):
        if kid is None or key.get("kid") == kid:
            return key
    return None


@lru_cache(maxsize=1)
def get_oidc_jwks() -> dict[str, Any]:
    issuer = settings.keycloak_issuer.rstrip("/")
    response = httpx.get(f"{issuer}/protocol/openid-connect/certs", timeout=5)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("OIDC JWKS response must be an object.")
    return payload


def extract_oidc_roles(payload: dict[str, Any]) -> list[str]:
    roles: set[str] = set()

    direct_roles = payload.get("roles")
    if isinstance(direct_roles, list):
        roles.update(str(role) for role in direct_roles)

    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict) and isinstance(realm_access.get("roles"), list):
        roles.update(str(role) for role in realm_access["roles"])

    resource_access = payload.get("resource_access")
    client_roles = None
    if isinstance(resource_access, dict):
        client_access = resource_access.get(settings.keycloak_client_id)
        if isinstance(client_access, dict):
            client_roles = client_access.get("roles")
    if isinstance(client_roles, list):
        roles.update(str(role) for role in client_roles)

    return sorted({normalize_oidc_role(role) for role in roles if normalize_oidc_role(role)})


def normalize_oidc_role(role: str) -> str | None:
    normalized = role.strip().lower().replace("verigraph_", "")
    if normalized in {user_role.value for user_role in UserRole}:
        return normalized
    return None


def extract_email_from_token_payload(payload: dict[str, Any]) -> str | None:
    for key in ("email", "preferred_username", "upn"):
        value = payload.get(key)
        if isinstance(value, str) and "@" in value:
            return value.strip().lower()
    return None


def select_token_role(payload: dict[str, Any]) -> UserRole | None:
    role_priority = [UserRole.ADMIN, UserRole.LEGAL, UserRole.ANALYST, UserRole.REPORTER]
    roles = set(str(role) for role in payload.get("roles") or [])
    for role in role_priority:
        if role.value in roles:
            return role
    return None
