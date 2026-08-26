"""
Proactive alerting — a generic Slack/Discord webhook sender.

One `alert_webhook_url` field per user (profiles.alert_webhook_url); format is
auto-detected from the URL at send time so users don't have to tell us which
service they're using. Both are free incoming-webhook integrations — no paid
API, no new account required beyond pasting a URL from Slack or Discord's own
"Integrations" settings.

Deliberately best-effort throughout: a failed or missing webhook must never
block or fail the upload pipeline it's reporting on.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 5.0  # seconds — this is a fire-and-forget notification, not a critical path


def _is_discord(url: str) -> bool:
    return "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url


async def send_alert(webhook_url: Optional[str], text: str) -> bool:
    """
    Post a plain-text alert to a Slack incoming-webhook or Discord webhook URL.
    Returns True on a 2xx response, False otherwise (including on any
    exception) -- callers should treat this as best-effort and never raise.
    """
    if not webhook_url:
        return False

    payload = {"content": text} if _is_discord(webhook_url) else {"text": text}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code >= 300:
                logger.warning(f"Alert webhook returned {resp.status_code}: {resp.text[:200]}")
                return False
            return True
    except Exception as e:
        logger.warning(f"Alert webhook send failed (non-fatal): {e}")
        return False


def format_regression_alert(cluster_title: str, resolved_title: str, confidence: float, upload_id: int) -> str:
    return (
        f"🔥 *Roast: fix didn't hold* — \"{resolved_title}\" was marked resolved, "
        f"but a new cluster (\"{cluster_title}\") matches it at {confidence:.0%} confidence. "
        f"Upload #{upload_id}."
    )


def format_critical_alert(cluster_title: str, review_count: int, upload_id: int) -> str:
    return (
        f"🚨 *Roast: new CRITICAL cluster* — \"{cluster_title}\" "
        f"({review_count} review{'s' if review_count != 1 else ''}). Upload #{upload_id}."
    )
