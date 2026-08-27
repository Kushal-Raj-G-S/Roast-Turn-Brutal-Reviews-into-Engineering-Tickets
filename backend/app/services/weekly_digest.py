"""
Weekly digest -- one email per user, covering every app they uploaded in
the past 7 days, sent every Monday morning. Runs in-process via
APScheduler (see main.py's lifespan) -- no external cron, no separate
worker process, no new infra beyond a pip package.

Best-effort per user: one user's send failing (bad email, Resend down)
must never stop the rest of the batch from going out.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.models.bulk_models import get_engine, Upload, Cluster
from app.models.models_supabase import Profile
from app.core.config import config
from app.services import notifications

logger = logging.getLogger(__name__)


async def send_weekly_digests() -> None:
    """
    For every profile with weekly_digest_enabled and at least one upload
    completed in the last 7 days, build and send one digest email
    summarizing all of them. Users with zero uploads in the window are
    skipped entirely -- an empty "nothing happened this week" email isn't
    worth sending.
    """
    engine = get_engine(config.DATABASE_URL)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    with Session(engine) as session:
        profiles = session.exec(
            select(Profile).where(Profile.weekly_digest_enabled == True)  # noqa: E712
        ).all()

        sent_count = 0
        for profile in profiles:
            try:
                uploads = session.exec(
                    select(Upload)
                    .where(Upload.user_id == profile.id)
                    .where(Upload.status == "completed")
                    .where(Upload.created_at >= cutoff)
                ).all()
                if not uploads:
                    continue

                app_summaries = []
                for upload in uploads:
                    clusters = session.exec(
                        select(Cluster).where(Cluster.upload_id == upload.id)
                    ).all()
                    app_summaries.append({
                        "app_name": (upload.filename or f"Upload #{upload.id}").rsplit(".", 1)[0],
                        "upload_id": upload.id,
                        "review_count": upload.total_reviews or 0,
                        "critical_count": sum(1 for c in clusters if (c.severity or "").lower() == "critical"),
                        "resolved_count": sum(1 for c in clusters if c.status == "resolved"),
                        "regression_count": sum(1 for c in clusters if c.regression_detected),
                    })

                subject, html = notifications.format_digest_email(app_summaries)
                sent, err = await notifications.send_email(profile.email, subject, html)
                if sent:
                    sent_count += 1
                else:
                    logger.warning(f"Weekly digest failed for {profile.email}: {err}")
            except Exception as e:
                # One user's malformed data must never take down the whole batch.
                logger.warning(f"Weekly digest error for profile {profile.id}: {e}")

        logger.info(f"📬 Weekly digest run complete: {sent_count}/{len(profiles)} eligible profiles sent")
