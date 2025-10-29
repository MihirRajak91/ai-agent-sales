from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.logging_config import get_logger
from app.models.auth import TenantClaims
from app.models.chat import ChatMessage, ChatRequest, ChatResponse
from app.models.intent import IntentClassification, IntentLabel
from app.models.retrieval import RetrievedChunk
from app.models.lead import Lead
from app.services import conversation as conversation_service
from app.services.intent import detect_intent
from app.services.lead import record_lead
from app.services.retrieval import query_knowledge_base
from app.services.scheduling import handle_scheduling, SchedulingResult
from app.settings import settings
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
    CHAT_PURCHASE_HEURISTIC_RATIONALE,
    CHAT_PURCHASE_KEYWORDS,
    CHAT_SCHEDULING_FAILURE_MESSAGE,
    CHAT_SOURCE_TEMPLATE,
    CHAT_SYSTEM_PROMPT,
    DEFAULT_CHAT_HISTORY_LIMIT,
    DEFAULT_RETRIEVAL_TOP_K,
)

logger = get_logger(CHAT_LOGGER_NAME)


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
    if lead:
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
        user_message = HumanMessage(
            content=_build_human_prompt(request.query, context_text),
        )

        llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL,
            api_key=settings.GEMINI_API_KEY,
            temperature=CHAT_MODEL_TEMPERATURE,
            max_output_tokens=CHAT_MODEL_MAX_OUTPUT_TOKENS,
        )

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
        answer_text = ai_response.content if isinstance(ai_response.content, str) else str(ai_response.content)

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


def _build_human_prompt(user_query: str, context_text: str) -> str:
    return (
        f"{CHAT_PROMPT_USER_QUESTION_TEMPLATE.format(question=user_query)}\n\n"
        f"{CHAT_PROMPT_CONTEXT_HEADER.format(context=context_text)}\n\n"
        f"{CHAT_PROMPT_INSTRUCTIONS}"
    )


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
