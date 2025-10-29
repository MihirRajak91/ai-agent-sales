from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Iterable

from email.utils import formataddr

from app.config.logging_config import get_logger
from app.config.settings import settings

logger = get_logger("email")


class EmailDeliveryError(RuntimeError):
    """Raised when an email cannot be delivered."""


def send_email(
    *,
    recipients: Iterable[str],
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> None:
    """
    Dispatch an email using the configured provider.
    Currently supports SMTP via the credentials provided in settings.
    """
    provider = settings.EMAIL_PROVIDER.lower()
    recipients = [addr.strip() for addr in recipients if addr.strip()]
    if not recipients:
        raise ValueError("At least one recipient email address is required")

    if provider == "smtp":
        _send_via_smtp(recipients=recipients, subject=subject, body=body, reply_to=reply_to)
    else:
        raise EmailDeliveryError(f"Email provider '{settings.EMAIL_PROVIDER}' is not supported yet")


def _send_via_smtp(
    *,
    recipients: list[str],
    subject: str,
    body: str,
    reply_to: str | None,
) -> None:
    msg = EmailMessage()
    from_address = formataddr((settings.EMAIL_FROM_NAME, settings.EMAIL_FROM_ADDRESS))
    msg["From"] = from_address
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
            logger.info(
                "Email sent",
                extra={"recipients": recipients, "subject": subject, "provider": "smtp"},
            )
    except Exception as exc:  # pragma: no cover - relies on external SMTP service
        logger.warning(
            "Failed to deliver email",
            extra={"recipients": recipients, "subject": subject, "provider": "smtp"},
            exc_info=exc,
        )
        raise EmailDeliveryError("SMTP delivery failed") from exc
