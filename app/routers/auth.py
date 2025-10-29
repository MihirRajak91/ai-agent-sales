from fastapi import APIRouter, HTTPException

from app.models.auth import TenantClaims, TokenRequest, TokenResponse
from app.services.auth import create_access_token
from app.config.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def issue_token(request: TokenRequest) -> TokenResponse:
    """Issue a short-lived JWT for local development and testing."""
    claims = TenantClaims(
        org_id=request.org_id,
        branch_id=request.branch_id,
        user_id=request.user_id,
        name=request.name,
    )
    token = create_access_token(claims, expires_delta=request.ttl_delta(settings.JWT_TTL_SECONDS))
    return TokenResponse(access_token=token)


@router.get("/token/dev", response_model=TokenResponse)
async def issue_dev_token() -> TokenResponse:
    """
    Issue a default development token so manual testing does not require crafting payloads.
    """
    if not settings.DEV_TOKEN_ENABLED or settings.APP_ENV != "development":
        raise HTTPException(status_code=403, detail="Dev token helper disabled")

    claims = TenantClaims(
        org_id=settings.DEV_TOKEN_ORG_ID,
        branch_id=settings.DEV_TOKEN_BRANCH_ID,
        user_id=settings.DEV_TOKEN_USER_ID,
        name=settings.DEV_TOKEN_NAME,
    )
    token = create_access_token(claims)
    return TokenResponse(access_token=token)
