from datetime import timedelta
from typing import Optional

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    org_id: str = Field(..., description="Tenant organization identifier")
    branch_id: str = Field(..., description="Tenant branch identifier")
    user_id: str = Field(..., description="User identifier for the chat operator")
    name: Optional[str] = Field(None, description="Optional display name for the user")
    ttl_seconds: Optional[int] = Field(
        None,
        ge=60,
        description="Optional override for token lifetime; defaults to JWT_TTL_SECONDS",
    )

    def ttl_delta(self, default_ttl: int) -> timedelta:
        ttl = self.ttl_seconds or default_ttl
        return timedelta(seconds=ttl)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TenantClaims(BaseModel):
    org_id: str
    branch_id: str
    user_id: str
    name: Optional[str] = None
