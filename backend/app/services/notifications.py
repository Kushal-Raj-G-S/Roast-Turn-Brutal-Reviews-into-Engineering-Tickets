"""
Proactive alerting — a generic Slack/Discord webhook sender, plus browser
Web Push (see send_push below).

One `alert_webhook_url` field per user (profiles.alert_webhook_url); format is
auto-detected from the URL at send time so users don't have to tell us which
service they're using. Both are free incoming-webhook integrations — no paid
API, no new account required beyond pasting a URL from Slack or Discord's own
"Integrations" settings.

Deliberately best-effort throughout: a failed or missing webhook must never
block or fail the upload pipeline it's reporting on.
"""

import json
import logging
from typing import Optional

import httpx
from pywebpush import webpush, WebPushException

from app.core.config import config

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


def upload_link(upload_id: int) -> str:
    """A real, clickable link to this upload's analytics page -- "Upload #45"
    on its own tells a reader nothing about which app or dataset that is."""
    return f"{config.FRONTEND_URL}/analytics?upload_id={upload_id}"


def format_batch_alert(
    app_name: str,
    upload_id: int,
    review_count: int,
    critical_items: list[tuple[str, int]],
    regression_items: list[tuple[str, str, float]],
) -> str:
    """
    One message for everything worth alerting on from a single upload,
    instead of one Discord/Slack message per finding -- a batch of 5+
    critical clusters previously meant 5+ separate pings for the same
    upload, which reads as spam rather than signal. Leads with WHAT app
    and WHICH upload (name + review count + a real clickable link), since
    "Upload #45" alone is meaningless days later with no context -- then
    itemizes each finding so nothing is lost by batching.

    critical_items: list of (cluster_title, review_count)
    regression_items: list of (cluster_title, resolved_title, confidence)
    """
    total = len(critical_items) + len(regression_items)
    header = (
        f"🔥 *Roast: {total} issue{'s' if total != 1 else ''} found in \"{app_name}\"* "
        f"({review_count} review{'s' if review_count != 1 else ''} analyzed)"
    )
    # A bare URL, not Slack's `<url|text>` link syntax -- Discord doesn't
    # understand that syntax and would show the pipe and label literally
    # instead of a clean link. A plain URL auto-linkifies on both Slack and
    # Discord, so this is the one form that works everywhere.
    link_line = f"Upload #{upload_id}: {upload_link(upload_id)}"

    lines = [header, link_line]

    if regression_items:
        lines.append(f"\n*Fix didn't hold ({len(regression_items)}):*")
        for cluster_title, resolved_title, confidence in regression_items:
            lines.append(
                f"• \"{resolved_title}\" was resolved, but \"{cluster_title}\" "
                f"matches it at {confidence:.0%} confidence"
            )

    if critical_items:
        lines.append(f"\n*New critical clusters ({len(critical_items)}):*")
        for cluster_title, item_review_count in critical_items:
            lines.append(
                f"• \"{cluster_title}\" "
                f"({item_review_count} review{'s' if item_review_count != 1 else ''})"
            )

    return "\n".join(lines)


def send_push(subscription: dict, title: str, body: str, url: Optional[str] = None) -> tuple[bool, bool]:
    """
    Deliver one Web Push notification to one browser subscription.
    Synchronous (pywebpush has no async API) -- the alert paths that use
    this already run in a background worker, not a request handler, so
    blocking briefly here is fine.

    `subscription` is the raw dict shape the browser's PushManager.subscribe()
    returns: {"endpoint": ..., "keys": {"p256dh": ..., "auth": ...}}.

    Returns (success, is_gone). `is_gone=True` means the push service
    returned 404/410 -- the browser unsubscribed or the subscription expired
    on its end, so the caller should delete the stored row rather than keep
    retrying a dead endpoint forever. Never raises -- same best-effort
    contract as send_alert, for the same reason: a dead push subscription
    must never block the pipeline reporting on it.
    """
    if not config.VAPID_PRIVATE_KEY or not config.VAPID_PUBLIC_KEY:
        return False, False

    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=config.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": config.VAPID_SUBJECT},
            timeout=_TIMEOUT,
        )
        return True, False
    except WebPushException as e:
        status = e.response.status_code if e.response is not None else None
        logger.warning(f"Push send failed (non-fatal, status={status}): {e}")
        return False, status in (404, 410)
    except Exception as e:
        logger.warning(f"Push send failed (non-fatal): {e}")
        return False, False
