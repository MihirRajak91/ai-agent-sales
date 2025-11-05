from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import uuid4

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app import deps
from app.logging_config import get_logger
from app.models.appointment import (
    AppointmentRequest,
    AppointmentResponse,
    AppointmentUpdateRequest,
)
from app.models.auth import TenantClaims
from app.models.lead import LeadStatus
from app.services.lead import attach_appointment
from app.settings import settings

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

logger = get_logger("calendar")


def _tokens_collection():
    db = deps.get_mongo_database()
    return db["google_tokens"]


def _state_collection():
    db = deps.get_mongo_database()
    return db["google_oauth_states"]


def _client_config() -> Dict[str, dict]:
    return {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uris": [settings.GOOGLE_OAUTH_REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def generate_authorization_url(tenant: TenantClaims) -> Dict[str, str]:
    state = uuid4().hex
    _state_collection().insert_one(
        {
            "state": state,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "user_id": tenant.user_id,
            "created_at": datetime.now(timezone.utc),
        }
    )

    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return {"authorization_url": auth_url, "state": state}


def exchange_code(state: str, code: str) -> TenantClaims:
    state_doc = _state_collection().find_one({"state": state})
    if not state_doc:
        raise ValueError("Invalid or expired OAuth state")

    tenant = TenantClaims(
        org_id=state_doc["org_id"],
        branch_id=state_doc["branch_id"],
        user_id=state_doc["user_id"],
        name=None,
    )

    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    flow.fetch_token(code=code)
    credentials = flow.credentials

    _tokens_collection().find_one_and_update(
        {
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
        },
        {
            "$set": {
                "org_id": tenant.org_id,
                "branch_id": tenant.branch_id,
                "user_id": tenant.user_id,
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
                "expiry": credentials.expiry,
                "updated_at": datetime.now(timezone.utc),
            },
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )

    _state_collection().delete_one({"state": state})
    logger.info(
        "Google OAuth tokens saved",
        extra={
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "user_id": tenant.user_id,
        },
    )
    return tenant


def token_status(tenant: TenantClaims) -> Dict[str, bool]:
    token_doc = _tokens_collection().find_one(
        {"org_id": tenant.org_id, "branch_id": tenant.branch_id}
    )
    return {"connected": bool(token_doc)}


def _load_credentials(tenant: TenantClaims) -> Credentials:
    token_doc = _tokens_collection().find_one(
        {"org_id": tenant.org_id, "branch_id": tenant.branch_id}
    )
    if not token_doc:
        raise ValueError("Google Calendar not linked for this tenant")

    creds = Credentials(
        token=token_doc.get("token"),
        refresh_token=token_doc.get("refresh_token"),
        token_uri=token_doc.get("token_uri"),
        client_id=token_doc.get("client_id"),
        client_secret=token_doc.get("client_secret"),
        scopes=token_doc.get("scopes"),
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _tokens_collection().update_one(
            {"_id": token_doc["_id"]},
            {
                "$set": {
                    "token": creds.token,
                    "expiry": creds.expiry,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        logger.info(
            "Google OAuth token refreshed",
            extra={"org_id": token_doc["org_id"], "branch_id": token_doc["branch_id"]},
        )

    return creds


def _calendar_service(creds: Credentials):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_appointment(
    tenant: TenantClaims,
    request: AppointmentRequest,
) -> AppointmentResponse:
    creds = _load_credentials(tenant)
    service = _calendar_service(creds)

    timezone_id = request.timezone or settings.DEFAULT_TIMEZONE
    event_body = {
        "summary": request.summary,
        "description": request.description,
        "start": {
            "dateTime": request.start_time.isoformat(),
            "timeZone": timezone_id,
        },
        "end": {"dateTime": request.end_time.isoformat(), "timeZone": timezone_id},
        "attendees": [{"email": email} for email in request.attendees],
    }
    if request.location:
        event_body["location"] = request.location

    calendar_id = request.calendar_id or "primary"
    event = (
        service.events()
        .insert(calendarId=calendar_id, body=event_body, sendUpdates="all")
        .execute()
    )
    logger.info(
        "Google Calendar event created",
        extra={
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "event_id": event.get("id"),
            "calendar_id": calendar_id,
        },
    )

    _maybe_attach_lead(
        tenant=tenant,
        lead_id=request.lead_id,
        event=event,
        calendar_id=calendar_id,
    )

    return _event_to_response(event, calendar_id)


def update_appointment(
    tenant: TenantClaims,
    event_id: str,
    request: AppointmentUpdateRequest,
) -> AppointmentResponse:
    creds = _load_credentials(tenant)
    service = _calendar_service(creds)

    calendar_id = request.calendar_id or "primary"
    existing = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

    timezone_id = request.timezone or existing.get("start", {}).get("timeZone", settings.DEFAULT_TIMEZONE)

    if request.summary is not None:
        existing["summary"] = request.summary
    if request.description is not None:
        existing["description"] = request.description
    if request.location is not None:
        existing["location"] = request.location
    if request.attendees is not None:
        existing["attendees"] = [{"email": email} for email in request.attendees]
    if request.start_time is not None:
        existing["start"] = {
            "dateTime": request.start_time.isoformat(),
            "timeZone": timezone_id,
        }
    if request.end_time is not None:
        existing["end"] = {
            "dateTime": request.end_time.isoformat(),
            "timeZone": timezone_id,
        }

    event = (
        service.events()
        .update(calendarId=calendar_id, eventId=event_id, body=existing, sendUpdates="all")
        .execute()
    )
    logger.info(
        "Google Calendar event updated",
        extra={
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "event_id": event.get("id"),
            "calendar_id": calendar_id,
        },
    )

    _maybe_attach_lead(
        tenant=tenant,
        lead_id=request.lead_id,
        event=event,
        calendar_id=calendar_id,
    )

    return _event_to_response(event, calendar_id)


def delete_appointment(
    tenant: TenantClaims,
    event_id: str,
    calendar_id: str = "primary",
) -> None:
    creds = _load_credentials(tenant)
    service = _calendar_service(creds)
    service.events().delete(calendarId=calendar_id, eventId=event_id, sendUpdates="all").execute()
    logger.info(
        "Google Calendar event deleted",
        extra={
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "event_id": event_id,
            "calendar_id": calendar_id,
        },
    )


def _event_to_response(event: dict, calendar_id: str) -> AppointmentResponse:
    return AppointmentResponse(
        event_id=event.get("id", ""),
        html_link=event.get("htmlLink"),
        status=event.get("status", "confirmed"),
        summary=event.get("summary"),
        start=event.get("start"),
        end=event.get("end"),
        calendar_id=calendar_id,
    )


def _maybe_attach_lead(
    *,
    tenant: TenantClaims,
    lead_id: Optional[str],
    event: dict,
    calendar_id: str,
) -> None:
    if not lead_id:
        return

    start_iso = event.get("start", {}).get("dateTime")
    end_iso = event.get("end", {}).get("dateTime")
    start_dt = _parse_datetime(start_iso)
    end_dt = _parse_datetime(end_iso)

    attach_appointment(
        tenant,
        lead_id=lead_id,
        event_id=event.get("id", ""),
        start=start_dt,
        end=end_dt,
        calendar_id=calendar_id,
        status=LeadStatus.CONTACTED,
    )


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)
