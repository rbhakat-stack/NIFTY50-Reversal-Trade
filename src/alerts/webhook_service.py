"""Optional Slack/generic webhook delivery for strategy alerts."""
from __future__ import annotations

import requests

from src import config
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class WebhookDeliveryError(RuntimeError):
    """Raised when an alert webhook cannot be delivered."""


def send_webhook(message: str, webhook_url: str | None = None, timeout: int = 10) -> None:
    webhook_url = webhook_url or config.ALERT_WEBHOOK_URL
    if not webhook_url:
        raise WebhookDeliveryError("ALERT_WEBHOOK_URL is not configured.")

    try:
        response = requests.post(webhook_url, json={"text": message}, timeout=timeout)
        response.raise_for_status()
        logger.info("Alert webhook delivered.")
    except requests.RequestException as exc:
        raise WebhookDeliveryError(f"Alert delivery failed: {exc}") from exc
