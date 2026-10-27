from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


UserRole = Literal["doctor", "admin"]


class Permission(StrEnum):
    CASE_READ = "case:read"
    CASE_WRITE = "case:write"
    CASE_REVIEW = "case:review"
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"
    SYSTEM_READ = "system:read"
    SYSTEM_MANAGE = "system:manage"
    INTEGRATION_READ = "integration:read"
    INTEGRATION_MANAGE = "integration:manage"
    USER_READ = "user:read"
    USER_MANAGE = "user:manage"
    AUDIT_READ = "audit:read"
    DATA_DICTIONARY_READ = "data_dictionary:read"
    DATA_DICTIONARY_MANAGE = "data_dictionary:manage"


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    "doctor": frozenset(
        {
            Permission.CASE_READ,
            Permission.CASE_WRITE,
            Permission.CASE_REVIEW,
            Permission.KNOWLEDGE_READ,
            Permission.SYSTEM_READ,
        }
    ),
    "admin": frozenset(Permission),
}


def permissions_for_role(role: UserRole) -> list[Permission]:
    return sorted(ROLE_PERMISSIONS[role], key=lambda permission: permission.value)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class UserRead(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole
    is_active: bool = True
    is_root: bool = False
    permissions: list[Permission] = Field(default_factory=list)


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=200)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=12, max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


class LoginResponse(BaseModel):
    user: UserRead
    expires_at: datetime


class SessionRead(BaseModel):
    id: str
    current: bool
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip_address: str = ""
    user_agent: str = ""


class AuthAuditEventRead(BaseModel):
    id: str
    event: str
    outcome: str
    username: str
    user_id: str | None
    actor_id: str | None
    ip_address: str
    user_agent: str
    detail: str
    created_at: datetime
