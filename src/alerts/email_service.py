"""SMTP email delivery for strategy alerts."""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from src import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class EmailDeliveryError(RuntimeError):
    """Raised when an alert email cannot be sent."""


def send_email(subject: str, body: str, recipient: str | None = None) -> None:
    recipient = recipient or config.ALERT_RECIPIENT_EMAIL
    if not (config.EMAIL_SENDER and config.EMAIL_PASSWORD and recipient):
        raise EmailDeliveryError(
            "EMAIL_SENDER, EMAIL_PASSWORD, and ALERT_RECIPIENT_EMAIL must be configured to send email alerts."
        )

    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = config.EMAIL_SENDER
    message["To"] = recipient

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
            server.sendmail(config.EMAIL_SENDER, [recipient], message.as_string())
        logger.info("Alert email sent to %s: %s", recipient, subject)
    except Exception as exc:
        raise EmailDeliveryError(f"Alert delivery failed: {exc}") from exc
