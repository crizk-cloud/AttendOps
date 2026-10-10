from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.auth.passwords import MIN_PASSWORD_LENGTH
from app.models import Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AppUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str | None
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


def _check_password(v: str | None) -> str | None:
    if v is not None and len(v) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return v


class AppUserCreate(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=200)
    password: str = Field(max_length=256)
    role: Role = Role.viewer

    _pw = field_validator("password")(_check_password)


class AppUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, max_length=256)

    _pw = field_validator("password")(_check_password)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)

    _pw = field_validator("new_password")(_check_password)
