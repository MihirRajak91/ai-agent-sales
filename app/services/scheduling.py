from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import Optional

from dateutil import parser, tz

from app.config.logging_config import get_logger
from app.models.appointment import AppointmentRequest, AppointmentUpdateRequest
from app.models.auth import TenantClaims
from app.models.intent import IntentLabel
from app.models.lead import Lead, LeadStatus
from app.services.google_calendar import (
    create_appointment,
    delete_appointment,
    update_appointment,
)
from app.services.email import EmailDeliveryError, send_email
from app.services.lead import attach_appointment, clear_appointment
from app.services.outreach import find_recipient_email
from app.config.settings import settings

EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

DEFAULT_APPOINTMENT_DURATION = timedelta(minutes=45)

logger = get_logger("scheduling")


@dataclass
class SchedulingResult:
    message: Optional[str] = None
    lead: Optional[Lead] = None


def handle_scheduling(
    tenant: TenantClaims,
    lead: Lead | None,
    user_message: str,
) -> SchedulingResult:
    if lead is None:
        return SchedulingResult()

    lowered = user_message.lower()
    email_hint = _extract_email(user_message)

    if "cancel" in lowered:
        return _handle_cancel(tenant, lead)

    if any(keyword in lowered for keyword in ["reschedule", "resched", "update", "move"]):
        return _handle_reschedule(tenant, lead, user_message, email_hint=email_hint)

    if lead.appointment_event_id:
        if (
            email_hint
            and lead.appointment_start
            and lead.appointment_end
            and lead.appointment_event_id
        ):
            recipient = _send_appointment_email(
                tenant=tenant,
                lead=lead,
                start=lead.appointment_start,
                end=lead.appointment_end,
                calendar_id=lead.calendar_id,
                event_id=lead.appointment_event_id,
                event_link=lead.appointment_html_link,
                summary=f"Demo with tenant {tenant.org_id}",
                action="booked",
                recipient_override=email_hint,
            )
            if recipient:
                return SchedulingResult(
                    message=f"Thanks! I've sent the confirmation to **{recipient}**.",
                    lead=lead,
                )
        return SchedulingResult()

    if lead.intent != IntentLabel.BOOK_APPOINTMENT.value:
        return SchedulingResult()

    return _handle_booking(tenant, lead, user_message, email_hint=email_hint)


def _handle_booking(
    tenant: TenantClaims,
    lead: Lead,
    user_message: str,
    email_hint: Optional[str] = None,
) -> SchedulingResult:
    start, end = _extract_datetimes(user_message)
    if not start or not end:
        return SchedulingResult(
            message=(
                "I can book that demo. Please share a specific date and time "
                "(e.g., 'next Tuesday at 3pm UTC' or 'May 6 at 10:00 AM PST')."
            )
        )

    timezone_name = settings.DEFAULT_TIMEZONE
    request = AppointmentRequest(
        summary=f"Demo with tenant {tenant.org_id}",
        description="Scheduled via conversational assistant.",
        start_time=start,
        end_time=end,
        timezone=timezone_name,
        attendees=[],
        lead_id=lead.id,
    )

    event = create_appointment(tenant, request)
    logger.info(
        "Appointment booked",
        extra={
            "lead_id": lead.id,
            "event_id": event.event_id,
            "calendar_id": event.calendar_id,
            "start": request.start_time.isoformat(),
            "end": request.end_time.isoformat(),
        },
    )
    updated_lead = attach_appointment(
        tenant,
        lead_id=lead.id,
        event_id=event.event_id,
        start=start,
        end=end,
        calendar_id=event.calendar_id,
        status=LeadStatus.CONTACTED,
        event_link=event.html_link,
    )

    recipient = _send_appointment_email(
        tenant=tenant,
        lead=updated_lead,
        start=start,
        end=end,
        calendar_id=event.calendar_id,
        event_id=event.event_id,
        event_link=event.html_link,
        summary=request.summary,
        action="booked",
        recipient_override=email_hint,
    )

    confirmation_suffix = (
        f" I've emailed a confirmation to **{recipient}**."
        if recipient
        else " Let me know the best email address so I can send a confirmation."
    )

    return SchedulingResult(
        message=(
            f"Demo scheduled for **{_format_datetime(start)}** "
            f"(event: [{event.event_id}]({event.html_link or 'calendar'}))."
            f"{confirmation_suffix}"
        ),
        lead=updated_lead,
    )


def _handle_reschedule(
    tenant: TenantClaims,
    lead: Lead,
    user_message: str,
    email_hint: Optional[str] = None,
) -> SchedulingResult:
    if not lead.appointment_event_id:
        return SchedulingResult(
            message="I couldn't find an existing appointment to reschedule. If you'd like to book one, please provide a time."
        )

    start, end = _extract_datetimes(user_message)
    if not start or not end:
        return SchedulingResult(
            message="To reschedule, please mention the new date and time."
        )

    request = AppointmentUpdateRequest(
        start_time=start,
        end_time=end,
        timezone=settings.DEFAULT_TIMEZONE,
        lead_id=lead.id,
        calendar_id=lead.calendar_id,
    )
    event = update_appointment(
        tenant,
        event_id=lead.appointment_event_id,
        request=request,
    )
    logger.info(
        "Appointment rescheduled",
        extra={
            "lead_id": lead.id,
            "event_id": event.event_id,
            "calendar_id": event.calendar_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
    )
    updated_lead = attach_appointment(
        tenant,
        lead_id=lead.id,
        event_id=event.event_id,
        start=start,
        end=end,
        calendar_id=event.calendar_id,
        status=LeadStatus.CONTACTED,
        event_link=event.html_link,
    )

    recipient = _send_appointment_email(
        tenant=tenant,
        lead=updated_lead,
        start=start,
        end=end,
        calendar_id=event.calendar_id,
        event_id=event.event_id,
        event_link=event.html_link,
        summary=request.summary or "Updated appointment",
        action="rescheduled",
        recipient_override=email_hint,
    )

    confirmation_suffix = (
        f" I've emailed the updated invite to **{recipient}**."
        if recipient
        else ""
    )

    return SchedulingResult(
        message=(
            f"Appointment updated to **{_format_datetime(start)}** "
            f"(event: [{event.event_id}]({event.html_link or 'calendar'}))."
            f"{confirmation_suffix}"
        ),
        lead=updated_lead,
    )


def _handle_cancel(
    tenant: TenantClaims,
    lead: Lead,
) -> SchedulingResult:
    if not lead.appointment_event_id:
        return SchedulingResult(
            message="There isn't a scheduled appointment to cancel."
        )

    delete_appointment(
        tenant,
        event_id=lead.appointment_event_id,
        calendar_id=lead.calendar_id or "primary",
    )
    updated_lead = clear_appointment(
        tenant,
        lead_id=lead.id,
        status=LeadStatus.OPEN,
    )
    logger.info(
        "Appointment cancelled",
        extra={
            "lead_id": lead.id,
            "event_id": lead.appointment_event_id,
            "calendar_id": lead.calendar_id,
        },
    )
    return SchedulingResult(
        message="The appointment has been cancelled. Let me know if you want to book a new time.",
        lead=updated_lead,
    )


def _extract_datetimes(message: str) -> tuple[Optional[datetime], Optional[datetime]]:
    try:
        default_tz = tz.gettz(settings.DEFAULT_TIMEZONE)
        now = datetime.now(default_tz)
        parsed = parser.parse(
            message,
            fuzzy=True,
            default=now.replace(hour=9, minute=0, second=0, microsecond=0),
        )
    except (parser.ParserError, ValueError, OverflowError):
        logger.warning(
            "Failed to parse datetime from message",
            extra={"message": message},
        )
        return None, None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)

    adjusted_forward = False
    if parsed <= datetime.now(parsed.tzinfo):
        parsed = parsed + timedelta(days=7)
        adjusted_forward = True

    end = parsed + DEFAULT_APPOINTMENT_DURATION
    logger.info(
        "Scheduling datetime parsed",
        extra={
            "start": parsed.isoformat(),
            "end": end.isoformat(),
            "timezone": settings.DEFAULT_TIMEZONE,
            "adjusted_forward_week": adjusted_forward,
        },
    )
    return parsed, end


def _format_datetime(value: datetime) -> str:
    local_tz = tz.gettz(settings.DEFAULT_TIMEZONE)
    localized = value.astimezone(local_tz)
    return localized.strftime("%A, %d %B %Y at %I:%M %p %Z")


def _format_duration(start: datetime, end: datetime) -> str:
    delta = end - start
    minutes = max(int(delta.total_seconds() // 60), 1)
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if mins:
        parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    return " ".join(parts) if parts else "45 minutes"


def _extract_email(text: str) -> Optional[str]:
    if not text:
        return None
    matches = EMAIL_REGEX.findall(text)
    return matches[-1].lower() if matches else None


def _send_appointment_email(
    *,
    tenant: TenantClaims,
    lead: Lead,
    start: datetime,
    end: datetime,
    calendar_id: Optional[str],
    event_id: str,
    event_link: Optional[str],
    summary: Optional[str],
    action: str,
    recipient_override: Optional[str] = None,
) -> Optional[str]:
    recipient = recipient_override or find_recipient_email(
        tenant, lead.conversation_id, history_limit=50
    )
    if not recipient:
        logger.info(
            "Skipping appointment email; no recipient detected",
            extra={
                "conversation_id": lead.conversation_id,
                "lead_id": lead.id,
                "action": action,
            },
        )
        return None

    when_text = _format_datetime(start)
    duration_text = _format_duration(start, end)
    summary_text = summary or "Sales appointment"
    action_phrase = "scheduled" if action == "booked" else "updated"
    subject = f"Your appointment is {action_phrase} for {when_text}"

    link_to_share = event_link or lead.appointment_html_link

    lines = [
        "Hi there,",
        "",
        f"We've {action_phrase} your appointment so everything is locked in.",
        "",
        f"- Summary: {summary_text}",
        f"- When: {when_text}",
        f"- Duration: {duration_text}",
        f"- Calendar: {calendar_id or 'primary'}",
    ]
    if link_to_share:
        lines.append(f"- Event link: {link_to_share}")
    else:
        lines.append("- Event link: This event is available in your Google Calendar.")

    lines.extend(
        [
            "",
            "If you need to make any changes or have questions, just reply to this email.",
            "",
            "Thanks,\nSales Team",
        ]
    )
    body = "\n".join(lines)

    try:
        send_email(recipients=[recipient], subject=subject, body=body)
        logger.info(
            "Appointment email sent",
            extra={
                "conversation_id": lead.conversation_id,
                "lead_id": lead.id,
                "recipient": recipient,
                "action": action,
                "event_id": event_id,
            },
        )
        return recipient
    except EmailDeliveryError as exc:
        logger.warning(
            "Failed to send appointment email",
            extra={
                "conversation_id": lead.conversation_id,
                "lead_id": lead.id,
                "recipient": recipient,
                "action": action,
                "event_id": event_id,
            },
            exc_info=exc,
        )
        return None

