from fastapi import APIRouter, Depends

from app.deps import get_current_tenant
from app.models.auth import TenantClaims

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    """Return a basic readiness payload for uptime checks."""
    return {"status": "ok"}


@router.get("/tenant")
async def tenant_health(claims: TenantClaims = Depends(get_current_tenant)) -> dict[str, str]:
    """Verify that tenant extraction from JWT works."""
    return {
        "status": "ok",
        "org_id": claims.org_id,
        "branch_id": claims.branch_id,
        "user_id": claims.user_id,
    }
