from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps import get_current_tenant
from app.models.auth import TenantClaims
from app.models.lead import Lead
from app.services import outreach
from app.utils.constants import OUTREACH_EMAIL_DEFAULT_HISTORY_LIMIT

router = APIRouter(prefix="/api/outreach", tags=["outreach"])


class ConversationMessagesResponse(BaseModel):
    conversation_id: str
    messages: List[dict]


class EmailDraftRequest(BaseModel):
    conversation_id: str = Field(..., description="Conversation identifier to build the draft for.")
    history_limit: Optional[int] = Field(
        default=OUTREACH_EMAIL_DEFAULT_HISTORY_LIMIT,
        ge=0,
        le=200,
        description="Number of most recent messages to include when generating the draft (0 means all).",
    )


class EmailDraftResponse(BaseModel):
    subject: str
    body: str
    suggested_recipient: Optional[str] = None
    lead_id: str
    conversation_id: str
    intent: Optional[str] = None
    latest_message: Optional[str] = None


class EmailSendRequest(BaseModel):
    conversation_id: str
    recipient: str
    subject: str
    body: str


@router.get("/open-leads", response_model=List[Lead])
async def get_open_leads(
    tenant: TenantClaims = Depends(get_current_tenant),
) -> List[Lead]:
    return outreach.list_open_leads(tenant)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationMessagesResponse,
)
async def get_conversation_history(
    conversation_id: str,
    limit: int = Query(
        OUTREACH_EMAIL_DEFAULT_HISTORY_LIMIT,
        ge=0,
        le=200,
        description="Number of most recent messages to return (0 means all).",
    ),
    tenant: TenantClaims = Depends(get_current_tenant),
) -> ConversationMessagesResponse:
    try:
        messages = outreach.get_conversation_messages(tenant, conversation_id, limit if limit != 0 else None)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ConversationMessagesResponse(conversation_id=conversation_id, messages=messages)


@router.post("/email/draft", response_model=EmailDraftResponse)
async def generate_email_draft(
    request: EmailDraftRequest,
    tenant: TenantClaims = Depends(get_current_tenant),
) -> EmailDraftResponse:
    try:
        draft = outreach.generate_email_draft(
            tenant,
            request.conversation_id,
            history_limit=request.history_limit,
        )
        return EmailDraftResponse(**draft)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/email/send")
async def send_email(
    request: EmailSendRequest,
    tenant: TenantClaims = Depends(get_current_tenant),
) -> dict:
    try:
        outreach.send_email_for_conversation(
            tenant,
            request.conversation_id,
            recipient=request.recipient,
            subject=request.subject,
            body=request.body,
        )
        return {"status": "sent"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
