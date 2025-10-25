from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse

from app.deps import get_current_tenant
from app.models.auth import TenantClaims
from app.services.google_calendar import (
    exchange_code,
    generate_authorization_url,
    token_status,
)

router = APIRouter(prefix="/oauth/google", tags=["google-oauth"])


@router.get("/init")
async def google_oauth_init(
    tenant: TenantClaims = Depends(get_current_tenant),
) -> dict[str, str]:
    return generate_authorization_url(tenant)


@router.get("/callback")
async def google_oauth_callback(request: Request) -> HTMLResponse:
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    if not state or not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth state or code",
        )

    tenant = exchange_code(state, code)
    return HTMLResponse(
        f"<html><body><h3>Google Calendar connected for org {tenant.org_id} / branch {tenant.branch_id}.</h3>"
        "<p>You can close this window.</p></body></html>"
    )


@router.get("/status")
async def google_oauth_status(
    tenant: TenantClaims = Depends(get_current_tenant),
) -> dict[str, bool]:
    return token_status(tenant)
