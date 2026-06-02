from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import EntityType, UserRole
from app.core.dependencies import require_report_reviewer
from app.core.security import decode_access_token, extract_email_from_token_payload, select_token_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.case import CaseCreate, CaseDetailResponse
from app.schemas.external_reputation import (
    ExternalReputationBatchCreate,
    ExternalReputationBatchResponse,
    ExternalReputationCheckResponse,
)
from app.schemas.risk import PublicRiskResponse
from app.services.cases import EntityNotFoundError
from app.services.cases import create_case_from_entity as create_case_from_entity_service
from app.services.cases import get_case_detail as get_case_detail_service
from app.services.external_reputation import (
    EntityNotFoundError as ExternalReputationEntityNotFoundError,
)
from app.services.external_reputation import (
    build_external_reputation_response,
    create_external_reputation_checks,
    list_external_reputation_checks,
)
from app.services.risk_lookup import lookup_public_risk
from app.services.users import find_or_create_external_user, find_user_by_email, find_user_by_id

router = APIRouter()


async def require_external_reputation_writer(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    token = extract_bearer_token(authorization)
    if settings.worker_api_token and token == settings.worker_api_token:
        return None

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error

    payload = decode_access_token(token)
    if payload is None or not payload.get("sub"):
        raise credentials_error

    if payload.get("auth_provider") == "keycloak":
        email = extract_email_from_token_payload(payload)
        if not email:
            raise credentials_error
        token_role = select_token_role(payload)
        if settings.keycloak_auto_provision_users:
            user = await find_or_create_external_user(db, email=email, role=token_role or UserRole.REPORTER)
        else:
            user = await find_user_by_email(db, email)
        if user is None:
            raise credentials_error
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user.")
        if user.role not in {UserRole.ADMIN.value, UserRole.ANALYST.value, UserRole.LEGAL.value}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
        return user

    try:
        user_id = UUID(str(payload["sub"]))
    except ValueError as exc:
        raise credentials_error from exc

    user = await find_user_by_id(db, user_id)
    if user is None:
        raise credentials_error
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user.")
    if user.role not in {UserRole.ADMIN.value, UserRole.ANALYST.value, UserRole.LEGAL.value}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
    return user


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


@router.get("/risk", response_model=PublicRiskResponse)
async def risk_lookup(
    value: str = Query(min_length=2, max_length=2000),
    entity_type: EntityType | None = None,
    db: AsyncSession = Depends(get_db),
) -> PublicRiskResponse:
    return await lookup_public_risk(db, value=value, entity_type=entity_type)


@router.post("/{entity_id}/case", response_model=CaseDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_case_from_entity(
    entity_id: UUID,
    payload: CaseCreate | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_report_reviewer),
) -> CaseDetailResponse:
    try:
        case = await create_case_from_entity_service(
            db,
            entity_id,
            payload,
            actor_user_id=current_user.id,
        )
        return await get_case_detail_service(db, case.id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found.") from exc


@router.get("/{entity_id}/external-reputation", response_model=list[ExternalReputationCheckResponse])
async def list_entity_external_reputation(
    entity_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    source: str | None = Query(default=None, min_length=1, max_length=80),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_report_reviewer),
) -> list[ExternalReputationCheckResponse]:
    checks = await list_external_reputation_checks(db, entity_id, limit=limit, source=source)
    return [build_external_reputation_response(check) for check in checks]


@router.post(
    "/{entity_id}/external-reputation",
    response_model=ExternalReputationBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_entity_external_reputation(
    entity_id: UUID,
    payload: ExternalReputationBatchCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = Depends(require_external_reputation_writer),
) -> ExternalReputationBatchResponse:
    try:
        result = await create_external_reputation_checks(db, entity_id, payload)
    except ExternalReputationEntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found.") from exc

    return ExternalReputationBatchResponse(
        checks=[build_external_reputation_response(check) for check in result.checks],
        summary=result.summary,
    )
