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


async def send_email(to_email: str, subject: str, html: str) -> tuple[bool, Optional[str]]:
    """
    Send one transactional email via Resend's REST API directly -- no SDK
    needed beyond httpx, which is already a dependency everywhere else in
    this file. Same best-effort contract as send_alert/send_push: never
    raises. Returns (success, error_detail) rather than a bare bool --
    unlike a webhook/push failure (which just gets logged in the
    background alert path), an interactive "send test email" click needs
    to surface *why* it failed. Resend's own free-tier restriction ("you
    can only send to your own signup address until a domain is verified")
    reads as a real, actionable error, not a generic "something broke."
    """
    if not config.RESEND_API_KEY:
        return False, "RESEND_API_KEY is not configured"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
                json={
                    "from": config.RESEND_FROM_EMAIL,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
            )
            if resp.status_code >= 300:
                detail = resp.text[:300]
                try:
                    detail = resp.json().get("message", detail)
                except Exception:
                    pass
                logger.warning(f"Resend send failed {resp.status_code}: {detail}")
                return False, detail
            return True, None
    except Exception as e:
        logger.warning(f"Email send failed (non-fatal): {e}")
        return False, str(e)


def _email_shell(inner_html: str) -> str:
    """Minimal, dependency-free HTML wrapper -- dark, on-brand, renders
    fine in every major email client without external CSS/fonts."""
    return f"""
    <div style="background:#0a0a0a;padding:32px 16px;font-family:-apple-system,Segoe UI,Roboto,sans-serif;">
      <div style="max-width:520px;margin:0 auto;background:#141414;border:1px solid #262626;border-radius:16px;overflow:hidden;">
        <div style="padding:20px 24px;border-bottom:1px solid #262626;">
          <span style="font-size:20px;font-weight:800;color:#f97316;">🔥 ROAST</span>
        </div>
        <div style="padding:24px;color:#e5e5e5;font-size:14px;line-height:1.6;">
          {inner_html}
        </div>
      </div>
    </div>
    """


def format_batch_alert_email(
    app_name: str,
    upload_id: int,
    review_count: int,
    critical_items: list[tuple[str, int]],
    regression_items: list[tuple[str, str, float]],
) -> tuple[str, str]:
    """HTML counterpart to format_batch_alert -- same content, same
    critical/regression split, rendered as an email instead of a chat
    message. Returns (subject, html)."""
    total = len(critical_items) + len(regression_items)
    subject = f"🔥 {total} issue{'s' if total != 1 else ''} found in \"{app_name}\""

    rows = ""
    if regression_items:
        rows += '<p style="font-weight:700;color:#c084fc;margin:16px 0 8px;">Fix didn\'t hold</p>'
        for cluster_title, resolved_title, confidence in regression_items:
            rows += (
                f'<p style="margin:4px 0;">• "{resolved_title}" was resolved, but '
                f'"{cluster_title}" matches it at {confidence:.0%} confidence</p>'
            )
    if critical_items:
        rows += '<p style="font-weight:700;color:#f87171;margin:16px 0 8px;">New critical clusters</p>'
        for cluster_title, item_review_count in critical_items:
            rows += (
                f'<p style="margin:4px 0;">• "{cluster_title}" '
                f"({item_review_count} review{'s' if item_review_count != 1 else ''})</p>"
            )

    link = upload_link(upload_id)
    inner = f"""
      <p style="margin:0 0 12px;">{review_count} review{'s' if review_count != 1 else ''} analyzed.</p>
      {rows}
      <a href="{link}" style="display:inline-block;margin-top:20px;padding:10px 20px;background:linear-gradient(90deg,#f97316,#dc2626);color:#fff;text-decoration:none;border-radius:10px;font-weight:600;">View Upload #{upload_id}</a>
    """
    return subject, _email_shell(inner)


def format_digest_email(app_summaries: list[dict]) -> tuple[str, str]:
    """
    Weekly digest -- one email covering every upload from the past 7 days
    across all the user's apps, not per-upload. app_summaries: list of
    {app_name, upload_id, review_count, critical_count, resolved_count,
    regression_count}.
    """
    total_reviews = sum(a["review_count"] for a in app_summaries)
    total_critical = sum(a["critical_count"] for a in app_summaries)
    subject = f"Your week on Roast — {total_reviews} reviews, {total_critical} critical issues"

    rows = ""
    for a in app_summaries:
        link = upload_link(a["upload_id"])
        rows += f"""
        <div style="margin:14px 0;padding:14px 16px;background:#0f0f0f;border:1px solid #262626;border-radius:12px;">
          <a href="{link}" style="color:#fb923c;font-weight:700;text-decoration:none;">{a['app_name']}</a>
          <p style="margin:6px 0 0;color:#a3a3a3;">
            {a['review_count']} reviews &middot;
            <span style="color:#f87171;">{a['critical_count']} critical</span> &middot;
            <span style="color:#4ade80;">{a['resolved_count']} resolved</span>
            {f' &middot; <span style="color:#c084fc;">{a["regression_count"]} regressions</span>' if a['regression_count'] else ''}
          </p>
        </div>
        """

    inner = f"""
      <p style="margin:0 0 16px;">Here's what happened across your apps this week:</p>
      {rows}
    """
    return subject, _email_shell(inner)
