from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, List, Optional, Tuple

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config.logging_config import get_logger
from app.models.auth import TenantClaims
from app.models.chat import ChatMessage, ChatRequest, ChatResponse
from app.models.intent import IntentClassification, IntentLabel
from app.models.retrieval import RetrievedChunk
from app.models.lead import Lead
from app.services import conversation as conversation_service
from app.services.email import EmailDeliveryError, send_email
from app.services.intent import detect_intent
from app.services.lead import record_lead
from app.services.retrieval import query_knowledge_base
from app.services.scheduling import handle_scheduling, SchedulingResult
from app.config.settings import settings
from app.utils.constants import (
    CHAT_BOOKING_HEURISTIC_RATIONALE,
    CHAT_BOOKING_KEYWORDS,
    CHAT_CONTEXT_SOURCE_FALLBACK,
    CHAT_INTENT_DETECTED_MESSAGE,
    CHAT_INTENT_HEURISTIC_CONFIDENCE,
    CHAT_LEAD_RECORD_FAILURE_MESSAGE,
    CHAT_LOGGER_NAME,
    CHAT_MESSAGE_ROLE_ASSISTANT,
    CHAT_MESSAGE_ROLE_USER,
    CHAT_MODEL_MAX_OUTPUT_TOKENS,
    CHAT_MODEL_TEMPERATURE,
    CHAT_NO_CONTEXT_MESSAGE,
    CHAT_PROMPT_CONTEXT_HEADER,
    CHAT_PROMPT_HISTORY_VARIABLE,
    CHAT_PROMPT_HUMAN_TEMPLATE,
    CHAT_PROMPT_INPUT_KEY,
    CHAT_PROMPT_INSTRUCTIONS,
    CHAT_PROMPT_USER_QUESTION_TEMPLATE,
    CHAT_PURCHASE_CONFIRMATION_KEYWORDS,
    CHAT_PURCHASE_HEURISTIC_RATIONALE,
    CHAT_PURCHASE_KEYWORDS,
    CHAT_PURCHASE_INVOICE_SYSTEM_PROMPT,
    CHAT_PURCHASE_INVOICE_USER_TEMPLATE,
    CHAT_PURCHASE_PAYMENT_INSTRUCTIONS,
    CHAT_PURCHASE_EMAIL_FAILURE_MESSAGE,
    CHAT_PURCHASE_EMAIL_MISSING_ADDRESS,
    CHAT_PURCHASE_EMAIL_SENT_TEMPLATE,
    CHAT_PURCHASE_EMAIL_SUBJECT,
    CHAT_PURCHASE_SALES_TONE_INSTRUCTIONS,
    CHAT_SCHEDULING_FAILURE_MESSAGE,
    CHAT_SOURCE_TEMPLATE,
    CHAT_SYSTEM_PROMPT,
    DEFAULT_CHAT_HISTORY_LIMIT,
    DEFAULT_RETRIEVAL_TOP_K,
)

logger = get_logger(CHAT_LOGGER_NAME)

_EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BOOKING_KEYWORDS = (
    "book",
    "schedule",
    "appointment",
    "meeting",
    "calendar",
    "time slot",
    "timeslot",
)
_RESCHEDULE_KEYWORDS = (
    "resched",
    "reschedule",
    "another time",
    "different time",
    "change the time",
    "change time",
    "move",
    "new time",
    "later time",
    "earlier time",
    "cancel",
)


def _build_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        api_key=settings.GEMINI_API_KEY,
        temperature=CHAT_MODEL_TEMPERATURE,
        max_output_tokens=CHAT_MODEL_MAX_OUTPUT_TOKENS,
    )


def handle_chat(
    tenant: TenantClaims,
    request: ChatRequest,
    *,
    history_limit: int = DEFAULT_CHAT_HISTORY_LIMIT,
    top_k: int = DEFAULT_RETRIEVAL_TOP_K,
) -> ChatResponse:
    conversation_id, recent_history = _prepare_conversation(tenant, request, history_limit)

    intent = _detect_user_intent(request.query, recent_history)

    lead = _maybe_record_lead(
        tenant=tenant,
        conversation_id=conversation_id,
        intent=intent,
        latest_message=request.query,
    )

    answer_text: str | None = None
    retrieval_matches: List[RetrievedChunk] = []
    lead_for_response: Lead | None = lead
    scheduling_result: SchedulingResult | None = None
    is_purchase_intent = intent is not None and intent.label == IntentLabel.PURCHASE
    purchase_confirmed = is_purchase_intent and _is_purchase_confirmation(request.query)
    if lead:
        lowered_query = request.query.lower()
        email_in_message = bool(_EMAIL_REGEX.search(request.query))
        wants_reschedule = any(phrase in lowered_query for phrase in _RESCHEDULE_KEYWORDS)
        wants_booking = any(phrase in lowered_query for phrase in _BOOKING_KEYWORDS)

        should_try_scheduling = False
        if intent and intent.label == IntentLabel.BOOK_APPOINTMENT:
            should_try_scheduling = True
        elif lead.appointment_event_id:
            if email_in_message or wants_reschedule:
                should_try_scheduling = True
        else:
            if email_in_message or wants_booking:
                should_try_scheduling = True

        if should_try_scheduling:
            try:
                scheduling_result = handle_scheduling(tenant, lead, request.query)
                if scheduling_result.message:
                    answer_text = scheduling_result.message
                if scheduling_result.lead:
                    lead_for_response = scheduling_result.lead
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    CHAT_SCHEDULING_FAILURE_MESSAGE,
                    extra={
                        "conversation_id": conversation_id,
                        "org_id": tenant.org_id,
                        "branch_id": tenant.branch_id,
                    },
                    exc_info=exc,
                )

    if answer_text is None:
        retrieval = query_knowledge_base(tenant, request.query, top_k=top_k)
        retrieval_matches = retrieval.matches
        context_text = _format_context(retrieval_matches)

        history_messages = _to_langchain_messages(recent_history)
        if purchase_confirmed:
            history_with_current = history_messages + [HumanMessage(content=request.query)]
            invoice_text = _generate_purchase_invoice(
                history_with_current,
                context_text,
                request.query,
            )
            email_feedback = _maybe_email_purchase_invoice(
                tenant=tenant,
                lead=lead_for_response or lead,
                conversation_id=conversation_id,
                history_messages=history_with_current,
                invoice_text=invoice_text,
            )
            answer_text = f"{invoice_text}\n\n{email_feedback}" if email_feedback else invoice_text
        else:
            user_message = HumanMessage(
                content=_build_human_prompt(request.query, context_text, intent),
            )

            llm = _build_llm()

            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", CHAT_SYSTEM_PROMPT),
                    MessagesPlaceholder(variable_name=CHAT_PROMPT_HISTORY_VARIABLE),
                    ("human", CHAT_PROMPT_HUMAN_TEMPLATE),
                ]
            )

            chain = prompt | llm
            ai_response: AIMessage = chain.invoke(
                {
                    CHAT_PROMPT_HISTORY_VARIABLE: history_messages,
                    CHAT_PROMPT_INPUT_KEY: user_message.content,
                }
            )
            answer_text = _extract_response_text(ai_response)
            if not answer_text.strip():
                answer_text = _fallback_response_from_sources(request.query, retrieval_matches)

    appended_messages = _persist_messages(
        tenant,
        conversation_id,
        user_content=request.query,
        assistant_content=answer_text,
    )

    response_history = _build_response_history(recent_history, appended_messages)

    return ChatResponse(
        conversation_id=conversation_id,
        answer=answer_text,
        sources=retrieval_matches,
        history=response_history,
        intent=intent,
        lead_id=lead_for_response.id if lead_for_response else None,
    )


def _prepare_conversation(
    tenant: TenantClaims,
    request: ChatRequest,
    history_limit: int,
) -> Tuple[str, List[dict]]:
    conversation_id = conversation_service.ensure_conversation(
        tenant,
        conversation_id=request.conversation_id,
        title=request.title,
    )

    history = []
    if request.conversation_id:
        history = conversation_service.get_recent_messages(
            tenant, conversation_id, limit=history_limit
        )
    else:
        # Newly created conversation has no history yet.
        history = []

    return conversation_id, history


def _format_context(chunks: List[RetrievedChunk]) -> str:
    if not chunks:
        return CHAT_NO_CONTEXT_MESSAGE

    lines = []
    for idx, chunk in enumerate(chunks, start=1):
        source = chunk.source or CHAT_CONTEXT_SOURCE_FALLBACK
        lines.append(
            CHAT_SOURCE_TEMPLATE.format(
                index=idx,
                page=chunk.page or "?",
                source=source,
                content=chunk.text,
            )
        )
    return "\n\n".join(lines)


def _fallback_response_from_sources(
    user_query: str, matches: List[RetrievedChunk], max_snippets: int = 3
) -> str:
    if not matches:
        return (
            "I'm still gathering the right information to answer that. "
            "Please make sure the relevant knowledge has been ingested, or share more details."
        )

    topic = user_query.strip()
    if topic:
        lines = [f"I'm still compiling a full answer about \"{topic}\". Here's what I can surface right now:"]
    else:
        lines = ["Here's what I can surface right now:"]
    for chunk in matches[:max_snippets]:
        source_name = chunk.source or CHAT_CONTEXT_SOURCE_FALLBACK
        snippet = (chunk.text or "").strip().replace("\n", " ")
        snippet = " ".join(snippet.split())
        if len(snippet) > 200:
            snippet = f"{snippet[:197]}..."
        lines.append(f"- {snippet} (source: {source_name})")

    return "\n".join(lines)


def _extract_response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    joined = _join_segments(_flatten_text_segments(content))

    if not joined and hasattr(response, "additional_kwargs"):
        joined = _join_segments(
            _flatten_text_segments(getattr(response, "additional_kwargs"))
        )

    if not joined and hasattr(response, "response_metadata"):
        joined = _join_segments(
            _flatten_text_segments(getattr(response, "response_metadata"))
        )

    return joined


def _flatten_text_segments(value: Any) -> List[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, (list, tuple, set)):
        collected: List[str] = []
        for item in value:
            collected.extend(_flatten_text_segments(item))
        return collected

    if isinstance(value, dict):
        collected: List[str] = []
        processed_keys: set[str] = set()
        if isinstance(value.get("text"), str):
            collected.append(value["text"])
            processed_keys.add("text")
        if "parts" in value:
            collected.extend(_flatten_text_segments(value["parts"]))
            processed_keys.add("parts")
        if "content" in value:
            collected.extend(_flatten_text_segments(value["content"]))
            processed_keys.add("content")
        for key, item in value.items():
            if key in processed_keys:
                continue
            collected.extend(_flatten_text_segments(item))
        return collected

    text_attr = getattr(value, "text", None)
    if isinstance(text_attr, str):
        return [text_attr]

    parts_attr = getattr(value, "parts", None)
    if parts_attr is not None:
        return _flatten_text_segments(parts_attr)

    content_attr = getattr(value, "content", None)
    if content_attr is not None and content_attr is not value:
        return _flatten_text_segments(content_attr)

    return [str(value)]


def _join_segments(segments: List[str]) -> str:
    filtered = _filter_summary_segments(segments)
    return " ".join(filtered).strip()


def _filter_summary_segments(segments: List[str]) -> List[str]:
    filtered: List[str] = []
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
        filtered.append(stripped)
    return filtered


def _to_langchain_messages(history: List[dict]) -> List[BaseMessage]:
    messages: List[BaseMessage] = []
    for item in history:
        role = item.get("role")
        content = item.get("content", "")
        if role == CHAT_MESSAGE_ROLE_ASSISTANT:
            messages.append(AIMessage(content=content))
        elif role == CHAT_MESSAGE_ROLE_USER:
            messages.append(HumanMessage(content=content))
    return messages


def _build_human_prompt(
    user_query: str,
    context_text: str,
    intent: IntentClassification | None,
) -> str:
    instructions = CHAT_PROMPT_INSTRUCTIONS
    if intent is not None and intent.label == IntentLabel.PURCHASE:
        instructions = f"{instructions}\n{CHAT_PURCHASE_SALES_TONE_INSTRUCTIONS}"
    return (
        f"{CHAT_PROMPT_USER_QUESTION_TEMPLATE.format(question=user_query)}\n\n"
        f"{CHAT_PROMPT_CONTEXT_HEADER.format(context=context_text)}\n\n"
        f"{instructions}"
    )


def _generate_purchase_invoice(
    history_messages: List[BaseMessage],
    context_text: str,
    user_message: str,
) -> str:
    llm = _build_llm()
    conversation_summary = _format_history_for_invoice(history_messages)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", CHAT_PURCHASE_INVOICE_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name=CHAT_PROMPT_HISTORY_VARIABLE),
            ("human", CHAT_PURCHASE_INVOICE_USER_TEMPLATE),
        ]
    )
    chain = prompt | llm
    ai_response: AIMessage = chain.invoke(
        {
            CHAT_PROMPT_HISTORY_VARIABLE: history_messages,
            "conversation_summary": conversation_summary,
            "context": context_text,
            "user_message": user_message,
            "payment_instructions": CHAT_PURCHASE_PAYMENT_INSTRUCTIONS,
        }
    )
    return ai_response.content if isinstance(ai_response.content, str) else str(ai_response.content)


def _maybe_email_purchase_invoice(
    *,
    tenant: TenantClaims,
    lead: Optional[Lead],
    conversation_id: str,
    history_messages: List[BaseMessage],
    invoice_text: str,
) -> Optional[str]:
    recipient = _extract_email_from_messages(history_messages)
    if not recipient:
        return CHAT_PURCHASE_EMAIL_MISSING_ADDRESS

    try:
        send_email(
            recipients=[recipient],
            subject=CHAT_PURCHASE_EMAIL_SUBJECT,
            body=invoice_text,
        )
        logger.info(
            "Invoice emailed",
            extra={
                "conversation_id": conversation_id,
                "recipient": recipient,
                "lead_id": getattr(lead, "id", None),
                "org_id": tenant.org_id,
                "branch_id": tenant.branch_id,
            },
        )
        return CHAT_PURCHASE_EMAIL_SENT_TEMPLATE.format(email=recipient)
    except EmailDeliveryError:
        logger.warning(
            "Failed to email invoice",
            extra={
                "conversation_id": conversation_id,
                "recipient": recipient,
                "lead_id": getattr(lead, "id", None),
                "org_id": tenant.org_id,
                "branch_id": tenant.branch_id,
            },
            exc_info=False,
        )
        return CHAT_PURCHASE_EMAIL_FAILURE_MESSAGE


def _format_history_for_invoice(messages: List[BaseMessage]) -> str:
    if not messages:
        return "None"
    lines: List[str] = []
    for message in messages[-10:]:
        if isinstance(message, HumanMessage):
            role = "User"
        elif isinstance(message, AIMessage):
            role = "Assistant"
        else:
            role = message.__class__.__name__
        lines.append(f"{role}: {getattr(message, 'content', '')}")
    return "\n".join(lines)


def _extract_email_from_messages(messages: List[BaseMessage]) -> Optional[str]:
    for message in reversed(messages):
        content = getattr(message, "content", "")
        if not isinstance(content, str):
            continue
        matches = _EMAIL_REGEX.findall(content)
        if matches:
            return matches[-1].lower()
    return None


def _persist_messages(
    tenant: TenantClaims,
    conversation_id: str,
    *,
    user_content: str,
    assistant_content: str,
) -> List[dict]:
    now = datetime.now(timezone.utc)
    messages = [
        {"role": CHAT_MESSAGE_ROLE_USER, "content": user_content, "timestamp": now},
        {"role": CHAT_MESSAGE_ROLE_ASSISTANT, "content": assistant_content, "timestamp": now},
    ]
    conversation_service.append_messages(tenant, conversation_id, messages)
    return messages


def _build_response_history(
    previous_history: List[dict],
    appended_messages: List[dict],
) -> List[ChatMessage]:
    history = previous_history + appended_messages
    return [
        ChatMessage(
            role=entry["role"],
            content=entry["content"],
            timestamp=entry.get("timestamp") or datetime.now(timezone.utc),
        )
        for entry in history
    ]


def _detect_user_intent(
    user_query: str,
    history: List[dict],
) -> IntentClassification:
    try:
        recent_user_messages = [
            entry.get("content", "")
            for entry in history
            if entry.get("role") == CHAT_MESSAGE_ROLE_USER
        ]
        intent = detect_intent(
            user_query=user_query,
            conversation_history=recent_user_messages,
        )
        if intent.label == IntentLabel.NONE:
            heuristic = _heuristic_intent(user_query)
            if heuristic:
                intent = heuristic
        logger.info(
            CHAT_INTENT_DETECTED_MESSAGE,
            extra={
                "intent": intent.label,
                "confidence": getattr(intent, "confidence", None),
                "conversation_history_len": len(history),
            },
        )
        return intent
    except Exception:
        return IntentClassification()


def _is_purchase_confirmation(user_query: str) -> bool:
    lowered = user_query.lower()
    return any(keyword in lowered for keyword in CHAT_PURCHASE_CONFIRMATION_KEYWORDS)


def _heuristic_intent(user_query: str) -> IntentClassification | None:
    lowered = user_query.lower()
    if any(word in lowered for word in CHAT_BOOKING_KEYWORDS):
        return IntentClassification(
            label=IntentLabel.BOOK_APPOINTMENT,
            confidence=CHAT_INTENT_HEURISTIC_CONFIDENCE,
            rationale=CHAT_BOOKING_HEURISTIC_RATIONALE,
        )
    if any(word in lowered for word in CHAT_PURCHASE_KEYWORDS):
        return IntentClassification(
            label=IntentLabel.PURCHASE,
            confidence=CHAT_INTENT_HEURISTIC_CONFIDENCE,
            rationale=CHAT_PURCHASE_HEURISTIC_RATIONALE,
        )
    return None


def _maybe_record_lead(
    *,
    tenant: TenantClaims,
    conversation_id: str,
    intent: IntentClassification,
    latest_message: str,
) -> Lead | None:
    if intent is None or intent.label == IntentLabel.NONE:
        return None

    try:
        lead = record_lead(
            tenant,
            conversation_id=conversation_id,
            intent=intent,
            latest_message=latest_message,
        )
        return lead
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(
            CHAT_LEAD_RECORD_FAILURE_MESSAGE,
            extra={
                "conversation_id": conversation_id,
                "org_id": tenant.org_id,
                "branch_id": tenant.branch_id,
            },
            exc_info=exc,
        )
        return None
