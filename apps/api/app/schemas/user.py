from datetime import datetime

from pydantic import BaseModel

from app.core.constants import UserRole


class UserListItem(BaseModel):
    id: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime | None


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserActiveUpdate(BaseModel):
    is_active: bool


class UserUpdateResponse(BaseModel):
    id: str
    email: str
    role: UserRole
    is_active: bool
    message: str
