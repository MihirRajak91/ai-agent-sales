from fastapi import APIRouter, Depends

from app.deps import get_current_tenant
from app.models.auth import TenantClaims
from app.models.lead import Lead
from app.services.lead import list_leads

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=list[Lead])
async def get_leads(tenant: TenantClaims = Depends(get_current_tenant)) -> list[Lead]:
    return list_leads(tenant)
