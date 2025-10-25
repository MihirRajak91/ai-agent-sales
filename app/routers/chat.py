from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_current_tenant
from app.models.auth import TenantClaims
from app.models.chat import ChatRequest, ChatResponse
from app.services.chat import handle_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    tenant: TenantClaims = Depends(get_current_tenant),
) -> ChatResponse:
    try:
        return handle_chat(tenant, request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
