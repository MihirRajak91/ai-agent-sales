from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from langchain_google_genai import ChatGoogleGenerativeAI

from app import deps
from app.config.logging_config import get_logger
from app.config.settings import settings
from app.models.auth import TenantClaims
from app.models.lead import Lead, LeadStatus
from app.models.retrieval import RetrievedChunk
from app.services.email import EmailDeliveryError, send_email
from app.services.lead import get_lead_by_conversation, list_leads
from app.services.retrieval import query_knowledge_base
from app.utils.constants import (
    DEFAULT_RETRIEVAL_TOP_K,
    OUTREACH_EMAIL_DEFAULT_HISTORY_LIMIT,
    OUTREACH_EMAIL_DEFAULT_SUBJECT,
    OUTREACH_EMAIL_SYSTEM_PROMPT,
    OUTREACH_EMAIL_TEMPLATE,
)

logger = get_logger("outreach")
EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def list_open_leads(tenant: TenantClaims) -> List[Lead]:
    return [lead for lead in list_leads(tenant) if lead.status == LeadStatus.OPEN]


def get_conversation_messages(
    tenant: TenantClaims,
    conversation_id: str,
    limit: Optional[int] = None,
) -> List[Dict[str, str]]:
    """
    Retrieve conversation messages for a tenant in chronological order.
    """
    db = deps.get_mongo_database()
    doc = db["conversations"].find_one(
        {
            "_id": conversation_id,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "user_id": tenant.user_id,
        }
    )
    if doc is None:
        raise ValueError("Conversation not found for tenant")

    messages: Sequence[dict] = doc.get("messages", [])
    if limit and limit > 0:
        messages = messages[-limit:]

    normalized: List[Dict[str, str]] = []
    for message in messages:
        timestamp = message.get("timestamp")
        if isinstance(timestamp, datetime):
            ts = timestamp.astimezone(timezone.utc).isoformat()
        else:
            ts = timestamp or ""
        normalized.append(
            {
                "role": message.get("role", "assistant"),
                "content": message.get("content", ""),
                "timestamp": ts,
            }
        )
    return normalized


def generate_email_draft(
    tenant: TenantClaims,
    conversation_id: str,
    history_limit: Optional[int] = None,
) -> Dict[str, object]:
    lead = get_lead_by_conversation(tenant, conversation_id)
    if lead is None:
        raise ValueError("No lead associated with this conversation yet.")

    limit = history_limit or OUTREACH_EMAIL_DEFAULT_HISTORY_LIMIT
    messages = get_conversation_messages(tenant, conversation_id, limit)
    conversation_summary = _format_conversation(messages)

    query_text = lead.latest_message or _latest_user_message(messages) or "Product information"
    retrieval = query_knowledge_base(tenant, query_text, top_k=DEFAULT_RETRIEVAL_TOP_K)
    context = _format_context(retrieval.matches)

    llm = _build_llm()
    prompt = (
        f"{OUTREACH_EMAIL_SYSTEM_PROMPT}\n\n"
        f"{OUTREACH_EMAIL_TEMPLATE.format(intent=lead.intent, latest_message=query_text, conversation_summary=conversation_summary, context=context)}"
    )
    response = llm.invoke(prompt)
    body = response.content if hasattr(response, "content") else str(response)

    suggested_recipient = _extract_email(messages)
    subject = _suggest_subject(lead)

    logger.info(
        "Generated outreach email draft",
        extra={
            "conversation_id": conversation_id,
            "lead_id": lead.id,
            "suggested_recipient": suggested_recipient,
        },
    )

    return {
        "subject": subject,
        "body": body,
        "suggested_recipient": suggested_recipient,
        "lead_id": lead.id,
        "conversation_id": conversation_id,
        "intent": lead.intent,
        "latest_message": query_text,
    }


def send_email_for_conversation(
    tenant: TenantClaims,
    conversation_id: str,
    *,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    lead = get_lead_by_conversation(tenant, conversation_id)
    if lead is None:
        raise ValueError("No lead associated with this conversation yet.")

    recipient = (recipient or "").strip()
    if not recipient:
        raise ValueError("Recipient email is required.")

    try:
        send_email(recipients=[recipient], subject=subject, body=body)
    except EmailDeliveryError as exc:
        logger.warning(
            "Failed to send outreach email",
            extra={
                "conversation_id": conversation_id,
                "lead_id": lead.id,
                "recipient": recipient,
            },
        )
        raise

    logger.info(
        "Outreach email sent",
        extra={
            "conversation_id": conversation_id,
            "lead_id": lead.id,
            "recipient": recipient,
        },
    )


def _build_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        api_key=settings.GEMINI_API_KEY,
        temperature=0.35,
        max_output_tokens=512,
    )


def _format_conversation(messages: Sequence[Dict[str, str]]) -> str:
    if not messages:
        return "- No prior conversation captured."
    lines: List[str] = []
    for item in messages:
        role = item.get("role", "assistant").title()
        content = (item.get("content") or "").strip()
        if content:
            lines.append(f"- {role}: {content}")
    return "\n".join(lines) if lines else "- No prior conversation captured."


def _format_context(chunks: List[RetrievedChunk]) -> str:
    if not chunks:
        return "- No knowledge base snippets were retrieved."
    lines = []
    for idx, chunk in enumerate(chunks, start=1):
        source = chunk.source or "knowledge base"
        page = chunk.page or "?"
        text = chunk.text.strip()
        lines.append(f"- [Snippet {idx}] (page {page} from {source}) {text}")
    return "\n".join(lines)


def _latest_user_message(messages: Sequence[Dict[str, str]]) -> Optional[str]:
    for item in reversed(messages):
        if item.get("role") == "user":
            content = (item.get("content") or "").strip()
            if content:
                return content
    return None


def _extract_email(messages: Sequence[Dict[str, str]]) -> Optional[str]:
    for item in reversed(messages):
        content = item.get("content") or ""
        match = EMAIL_REGEX.findall(content)
        if match:
            return match[-1].lower()
    return None


def _suggest_subject(lead: Lead) -> str:
    intent = (lead.intent or "").replace("_", " ").strip()
    if intent:
        return f"Next steps on your {intent}"
    return OUTREACH_EMAIL_DEFAULT_SUBJECT


def find_recipient_email(
    tenant: TenantClaims,
    conversation_id: str,
    history_limit: Optional[int] = None,
) -> Optional[str]:
    try:
        messages = get_conversation_messages(tenant, conversation_id, history_limit)
    except ValueError:
        return None
    return _extract_email(messages)


__all__ = [
    "list_open_leads",
    "get_conversation_messages",
    "generate_email_draft",
    "send_email_for_conversation",
    "find_recipient_email",
]
