from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, List, Optional, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from app.models.intent import IntentClassification, IntentLabel
from app.settings import settings


class IntentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    result: Optional[IntentClassification]


INTENT_SYSTEM_PROMPT = """You are an intent classification assistant for sales conversations.
Classify the user's latest request into one of three intents:
- "book_appointment": user wants to schedule a meeting, demo, or callback.
- "purchase": user wants pricing, to sign up, or to buy.
- "none": anything else.
Return only JSON with keys {"intent": "...", "confidence": <0-1>, "rationale": "..."}.
Do NOT include markdown, explanations, or additional text."""


@lru_cache(maxsize=1)
def _intent_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        api_key=settings.GEMINI_API_KEY,
        temperature=0.2,
        max_output_tokens=256,
    )


@lru_cache(maxsize=1)
def _intent_graph():
    graph = StateGraph(IntentState)
    graph.add_node("classify", _classify_node)
    graph.set_entry_point("classify")
    graph.add_edge("classify", END)
    return graph.compile()


def detect_intent(
    *,
    user_query: str,
    conversation_history: Optional[List[str]] = None,
) -> IntentClassification:
    """
    Run a LangGraph-powered Gemini classification to detect booking/purchase intent.
    """
    historySnippet = "\n".join(f"- {msg}" for msg in (conversation_history or [])[-3:])
    human_prompt = (
        "Classify the intent of the final user message.\n"
        f"Recent user messages:\n{historySnippet or 'None'}\n"
        f"Final user message:\n{user_query}\n"
        'Respond ONLY with the JSON object schema described previously.'
    )

    initial_state: IntentState = {
        "messages": [
            SystemMessage(content=INTENT_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ],
        "result": None,
    }

    graph = _intent_graph()
    output = graph.invoke(initial_state)
    result = output.get("result")

    if isinstance(result, IntentClassification):
        return result
    return IntentClassification()


def _classify_node(state: IntentState) -> IntentState:
    llm = _intent_llm()
    response = llm.invoke(state["messages"])
    parsed = _parse_intent(response.content if hasattr(response, "content") else response)
    updated_state: IntentState = {
        "messages": [response],
        "result": parsed,
    }
    return updated_state


def _parse_intent(content: str) -> IntentClassification:
    try:
        data = json.loads(content)
        intent_raw = str(data.get("intent", "none")).lower()
        if intent_raw not in {label.value for label in IntentLabel}:
            intent_raw = IntentLabel.NONE.value
        label = IntentLabel(intent_raw)
        confidence = float(data.get("confidence", 0))
        confidence = max(0.0, min(1.0, confidence))
        rationale = data.get("rationale")
        return IntentClassification(label=label, confidence=confidence, rationale=rationale)
    except Exception:
        return IntentClassification()
