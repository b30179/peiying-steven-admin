from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)


class PrincipalView(BaseModel):
    user_id: str
    username: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    auth_mode: str


class AccountCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=500)
    roles: list[str] = Field(min_length=1)


class AccountRolesRequest(BaseModel):
    roles: list[str] = Field(min_length=1)


class UserSettingsUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    locale: str = Field(pattern=r"^zh-(TW|CN)$")


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=500)
    new_password: str = Field(min_length=6, max_length=500)