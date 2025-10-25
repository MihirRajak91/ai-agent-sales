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

logger = get_logger("chat")

SYSTEM_PROMPT = """You are a helpful sales assistant for internal teams.
Answer the user's question using ONLY the provided knowledge base context and prior conversation.
If the context does not contain the answer, reply with a brief apology and ask for more information.
Reference source numbers in parentheses (e.g., [source 1]) when quoting from specific chunks."""


def handle_chat(
    tenant: TenantClaims,
    request: ChatRequest,
    *,
    history_limit: int = 6,
    top_k: int = 6,
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
                "Scheduling handling failed",
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
            temperature=0.3,
            max_output_tokens=512,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}"),
            ]
        )

        chain = prompt | llm
        ai_response: AIMessage = chain.invoke(
            {
                "history": history_messages,
                "input": user_message.content,
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
        return "No relevant knowledge base entries were retrieved for this question."

    lines = []
    for idx, chunk in enumerate(chunks, start=1):
        source = chunk.source or "knowledge base"
        lines.append(f"[source {idx}] (page {chunk.page or '?'} from {source})\n{chunk.text}")
    return "\n\n".join(lines)


def _to_langchain_messages(history: List[dict]) -> List[BaseMessage]:
    messages: List[BaseMessage] = []
    for item in history:
        role = item.get("role")
        content = item.get("content", "")
        if role == "assistant":
            messages.append(AIMessage(content=content))
        elif role == "user":
            messages.append(HumanMessage(content=content))
    return messages


def _build_human_prompt(user_query: str, context_text: str) -> str:
    return (
        f"User question: {user_query}\n\n"
        f"Knowledge base context:\n{context_text}\n\n"
        "Provide a concise answer grounded in the context above.\n"
        "If you mention a source, cite it as [source number]."
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
        {"role": "user", "content": user_content, "timestamp": now},
        {"role": "assistant", "content": assistant_content, "timestamp": now},
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
            if entry.get("role") == "user"
        ]
        intent = detect_intent(
            user_query=user_query,
            conversation_history=recent_user_messages,
        )
        if intent.label == IntentLabel.NONE:
            heuristic = _heuristic_intent(user_query)
            if heuristic:
                intent = heuristic
        return intent
    except Exception:
        return IntentClassification()


def _heuristic_intent(user_query: str) -> IntentClassification | None:
    lowered = user_query.lower()
    booking_keywords = ["book", "schedule", "demo", "meeting", "appointment"]
    purchase_keywords = ["buy", "purchase", "pricing", "quote", "license"]

    if any(word in lowered for word in booking_keywords):
        return IntentClassification(
            label=IntentLabel.BOOK_APPOINTMENT,
            confidence=0.6,
            rationale="Keyword heuristic detected booking intent.",
        )
    if any(word in lowered for word in purchase_keywords):
        return IntentClassification(
            label=IntentLabel.PURCHASE,
            confidence=0.6,
            rationale="Keyword heuristic detected purchase intent.",
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
            "Failed to record lead",
            extra={
                "conversation_id": conversation_id,
                "org_id": tenant.org_id,
                "branch_id": tenant.branch_id,
            },
            exc_info=exc,
        )
        return None
