from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.models.intent import IntentClassification
from app.models.retrieval import RetrievedChunk


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    conversation_id: Optional[str] = Field(
        default=None,
        description="Existing conversation identifier; omit to start a new conversation.",
    )
    title: Optional[str] = Field(
        default=None,
        description="Optional title to assign when creating a new conversation.",
    )


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: List[RetrievedChunk]
    history: List[ChatMessage]
    intent: IntentClassification | None = None
    lead_id: str | None = Field(
        default=None, description="Lead identifier if the turn generated or updated a lead."
    )
