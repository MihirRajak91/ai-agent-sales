from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class AppointmentRequest(BaseModel):
    summary: str = Field(..., description="Event title displayed on the calendar.")
    description: Optional[str] = Field(default=None, description="Additional context for the meeting.")
    start_time: datetime = Field(..., description="Start time in ISO 8601 with timezone.")
    end_time: datetime = Field(..., description="End time in ISO 8601 with timezone.")
    timezone: Optional[str] = Field(default=None, description="IANA timezone. Defaults to tenant default.")
    attendees: List[EmailStr] = Field(default_factory=list, description="List of attendee email addresses.")
    location: Optional[str] = None
    lead_id: Optional[str] = Field(default=None, description="Attach scheduling outcome to an existing lead.")
    calendar_id: Optional[str] = Field(default="primary", description="Calendar identifier; defaults to primary.")


class AppointmentUpdateRequest(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    timezone: Optional[str] = None
    attendees: Optional[List[EmailStr]] = None
    location: Optional[str] = None
    calendar_id: Optional[str] = None
    lead_id: Optional[str] = Field(default=None, description="Update associated lead if supplied.")


class AppointmentResponse(BaseModel):
    event_id: str
    html_link: Optional[str] = None
    status: str
    summary: Optional[str] = None
    start: Optional[dict] = None
    end: Optional[dict] = None
    calendar_id: str = "primary"
