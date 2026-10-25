from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


UserRole = Literal["doctor", "admin"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class UserRead(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole


class LoginResponse(BaseModel):
    user: UserRead
    expires_at: datetime
