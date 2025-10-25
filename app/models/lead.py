from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LeadStatus(str, Enum):
    OPEN = "open"
    CONTACTED = "contacted"
    CLOSED = "closed"


class LeadSource(str, Enum):
    CHAT = "chat"


class Lead(BaseModel):
    id: str = Field(..., description="Lead identifier (_id from Mongo).")
    org_id: str
    branch_id: str
    user_id: str
    conversation_id: str
    intent: str
    latest_message: str
    status: LeadStatus = LeadStatus.OPEN
    source: LeadSource = LeadSource.CHAT
    created_at: datetime
    updated_at: datetime
    notes: Optional[str] = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: Optional[str] = None
    appointment_event_id: Optional[str] = None
    appointment_start: Optional[datetime] = None
    appointment_end: Optional[datetime] = None
    calendar_id: Optional[str] = None
