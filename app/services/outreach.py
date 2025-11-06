from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

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
    body = _extract_response_text(response)
    if not body.strip():
        body = _fallback_email_body(
            lead.intent,
            query_text,
            retrieval.matches,
            conversation_summary,
        )

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


def _fallback_email_body(
    intent: Optional[str],
    latest_message: str,
    matches: List[RetrievedChunk],
    conversation_summary: str,
) -> str:
    greeting = "Hi there,"
    topic = latest_message.strip() or "pricing"
    intent_text = (intent or "").replace("_", " ").strip()
    opener_bits = [f"Thanks for reaching out about {topic}."]
    if intent_text:
        opener_bits.append(f"We're excited to support your {intent_text} plans.")
    opener = " ".join(opener_bits)

    highlights = _build_highlights(matches)
    if not highlights:
        highlights = [
            "Starter: Launch quickly with up to 5 seats, core connectors, and email support for $750/month or $8,100/year.",
            "Growth: Give larger teams 20 seats, higher usage limits, advanced integrations, and standard SLA coverage for $2,500/month.",
            "Professional: Enterprise controls, optional private VPC deployment, and premium support tailored to regulated industries.",
        ]

    lines = [
        greeting,
        "",
        opener,
        "",
        "Here's a quick snapshot of how teams typically get started:",
        "",
        "Plan highlights:",
    ]
    lines.extend(f"- {highlight}" for highlight in highlights)
    lines.extend(
        [
            "",
            "Where we can help next:",
            "- Share your seat count and expected usage so we can tailor a quote.",
            "- Let us know if you prefer SaaS, private VPC, or on-prem deployment.",
            "- Happy to schedule a quick call to review commercials and timelines.",
            "",
            "Looking forward to partnering with you.",
            "",
            "Best regards,\nSales Team",
        ]
    )
    return "\n".join(lines)


def _build_highlights(matches: List[RetrievedChunk], limit: int = 3) -> List[str]:
    highlights: List[str] = []
    for chunk in matches[:limit]:
        snippet = (chunk.text or "").strip().replace("\n", " ")
        snippet = " ".join(snippet.split())
        if not snippet:
            continue
        if len(snippet) > 200:
            snippet = f"{snippet[:197]}..."
        highlights.append(snippet)
    return highlights


def _extract_response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    joined = _join_segments(_flatten_segments(content))

    if not joined and hasattr(response, "additional_kwargs"):
        joined = _join_segments(
            _flatten_segments(getattr(response, "additional_kwargs"))
        )

    if not joined and hasattr(response, "response_metadata"):
        joined = _join_segments(
            _flatten_segments(getattr(response, "response_metadata"))
        )

    return joined


def _flatten_segments(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        collected: List[str] = []
        for item in value:
            collected.extend(_flatten_segments(item))
        return collected
    if isinstance(value, dict):
        collected: List[str] = []
        processed: set[str] = set()
        if isinstance(value.get("text"), str):
            collected.append(value["text"])
            processed.add("text")
        if "parts" in value and "parts" not in processed:
            collected.extend(_flatten_segments(value["parts"]))
            processed.add("parts")
        if "content" in value and "content" not in processed:
            collected.extend(_flatten_segments(value["content"]))
            processed.add("content")
        for key, item in value.items():
            if key in processed:
                continue
            collected.extend(_flatten_segments(item))
        return collected

    text_attr = getattr(value, "text", None)
    if isinstance(text_attr, str):
        return [text_attr]
    parts_attr = getattr(value, "parts", None)
    if parts_attr is not None:
        return _flatten_segments(parts_attr)
    content_attr = getattr(value, "content", None)
    if content_attr is not None and content_attr is not value:
        return _flatten_segments(content_attr)
    return [str(value)]


def _join_segments(segments: List[str]) -> str:
    filtered = _filter_segments(segments)
    return " ".join(filtered).strip()


def _filter_segments(segments: List[str]) -> List[str]:
    cleaned: List[str] = []
    for segment in segments:
        if not segment:
            continue
        stripped = segment.strip()
        if not stripped:
            continue
        if not any(ch.isalpha() for ch in stripped):
            continue
        if stripped.isupper() and len(stripped.split()) == 1:
            continue
        cleaned.append(stripped)
    return cleaned


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
