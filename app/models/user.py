from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Plaintext password provided during registration.")
    org_id: str
    branch_id: str
    name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class User(BaseModel):
    id: str
    email: EmailStr
    org_id: str
    branch_id: str
    name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
