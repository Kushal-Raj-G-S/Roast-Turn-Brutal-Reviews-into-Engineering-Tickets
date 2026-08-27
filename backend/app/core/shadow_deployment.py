"""
Shadow Deployment Integration for Production Backend.

Automatically runs v1 (production) + v2 (shadow) + v3 (monitoring) in parallel
on every upload, providing real-time architecture validation.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List

import numpy as np

from app.models.bulk_models import Upload, Cluster
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

# ── regression detection ──────────────────────────────────────────────────────

def _title_similarity(a: str, b: str) -> float:
    """
    Token-level Jaccard similarity between two cluster titles.
    Ignores common stop-words for better signal.
    """
    _STOP = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "is", "are", "was", "were", "not", "issue", "issues",
        "problem", "problems", "error", "errors", "app", "users", "user",
        "when", "after", "during", "while",
    }
    wa = set(a.lower().split()) - _STOP
    wb = set(b.lower().split()) - _STOP
    if not wa or not wb:
        return 0.0
    intersection = len(wa & wb)
    union = len(wa | wb)
    return intersection / union if union > 0 else 0.0


def _cluster_text(c: Cluster) -> str:
    """Same title+keywords composition vector_store.py uses to index a cluster,
    so this similarity is directly comparable to what hybrid_search would find."""
    return f"{c.title} {' '.join(c.keywords or [])}"


def _semantic_similarities(new_clusters: List[Cluster], resolved_clusters: List[Cluster]) -> Optional[np.ndarray]:
    """
    Pairwise cosine similarity between every new cluster and every resolved
    cluster, via the same local embedding backend used everywhere else in the
    pipeline (bulk_embedding.py) -- no network call, no extra API cost.
    Returns an (len(new), len(resolved)) matrix, or None if embedding is
    unavailable for any reason (caller falls back to Jaccard-only).
    """
    try:
        from app.services.bulk_embedding import EmbeddingBackend
        backend = EmbeddingBackend()
        texts = [_cluster_text(c) for c in new_clusters] + [_cluster_text(c) for c in resolved_clusters]
        vecs = backend.encode_batch(texts)
        if vecs is None or len(vecs) != len(texts):
            return None
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = vecs / norms
        new_vecs = vecs[: len(new_clusters)]
        resolved_vecs = vecs[len(new_clusters):]
        return new_vecs @ resolved_vecs.T
    except Exception as e:
        logger.warning(f"Semantic regression matching unavailable, Jaccard-only this run ({e})")
        return None


# A cluster whose title shares almost no words with a resolved one ("crashes
# on login" vs "freezes when signing in") still scores ~0 on Jaccard but well
# above this on cosine similarity of a sentence embedding -- this threshold
# is what actually catches paraphrased recurrences of the same underlying bug.
_SEMANTIC_REGRESSION_THRESHOLD = 0.62


def _detect_regressions(
    session: Session,
    new_cluster_ids: List[int],
    upload_id: int,
    user_id,
) -> None:
    """
    Compare newly-created clusters against all resolved clusters from this user's
    PREVIOUS uploads -- the "fix verification loop": a cluster marked `resolved`
    that resurfaces in a later upload means the fix didn't actually hold.

    Two independent signals are combined, since they catch different things:
    - Jaccard title-word overlap: cheap, catches near-identical titles.
    - Semantic cosine similarity (local sentence embeddings): catches the same
      bug described in different words, which Jaccard has zero chance on.
    Either signal crossing its threshold marks a regression; the stored
    `regression_confidence` is the max of the two, so the UI can show how
    confident the match actually is instead of a bare yes/no.

    Runs synchronously inside the background thread (no await needed).
    """
    # 1. Resolved clusters from user's previous uploads (exclude current upload)
    prev_upload_ids: List[int] = list(
        session.exec(
            select(Upload.id)
            .where(Upload.user_id == user_id)
            .where(Upload.status == "completed")
            .where(Upload.id != upload_id)
        ).all()
    )
    if not prev_upload_ids:
        return

    resolved_clusters = list(
        session.exec(
            select(Cluster)
            .where(Cluster.upload_id.in_(prev_upload_ids))
            .where(Cluster.status == "resolved")
        ).all()
    )
    if not resolved_clusters:
        return

    # 2. New clusters for this upload
    new_clusters = list(
        session.exec(
            select(Cluster).where(Cluster.id.in_(new_cluster_ids))
        ).all()
    )
    if not new_clusters:
        return

    semantic_matrix = _semantic_similarities(new_clusters, resolved_clusters)

    regression_count = 0
    for i, nc in enumerate(new_clusters):
        best_jaccard = 0.0
        best_semantic = 0.0
        best_match: Optional[Cluster] = None
        for j, rc in enumerate(resolved_clusters):
            jaccard = _title_similarity(nc.title, rc.title)
            semantic = float(semantic_matrix[i, j]) if semantic_matrix is not None else 0.0
            combined_best_for_this_pair = max(jaccard, semantic)
            if combined_best_for_this_pair > max(best_jaccard, best_semantic):
                best_jaccard = jaccard
                best_semantic = semantic
                best_match = rc

        is_regression = best_jaccard >= 0.40 or best_semantic >= _SEMANTIC_REGRESSION_THRESHOLD
        if best_match and is_regression:
            confidence = max(best_jaccard, best_semantic)
            method = (
                "keyword+semantic" if (best_jaccard >= 0.40 and best_semantic >= _SEMANTIC_REGRESSION_THRESHOLD)
                else "semantic" if best_semantic >= _SEMANTIC_REGRESSION_THRESHOLD
                else "keyword"
            )
            nc.regression_detected = True
            nc.regression_of_title = best_match.title
            nc.regression_confidence = round(confidence, 3)
            nc.regression_match_method = method
            nc.regression_resolved_at = best_match.resolved_at
            session.add(nc)
            regression_count += 1
            logger.warning(
                f"↩ REGRESSION detected: cluster {nc.id} '{nc.title}' matches resolved "
                f"'{best_match.title}' (confidence={confidence:.2f}, method={method})"
            )

    if regression_count:
        session.commit()
        logger.info(f"Regression check: {regression_count} regression(s) flagged for upload {upload_id}")
    else:
        logger.info(f"Regression check: no regressions found for upload {upload_id}")


async def _send_upload_alerts(session: Session, upload: Upload, clusters: List[Cluster]) -> None:
    """
    Proactive alerting: notify the user for the two events actually worth
    interrupting someone for -- a fix that didn't hold, and a brand-new
    CRITICAL cluster. Three independent channels, each with its own gate:
    Slack/Discord webhook + browser Web Push share profile.alerts_enabled,
    while email has its own profile.email_alerts_enabled -- a user can want
    Discord/push on but email off (or vice versa), so these aren't the same
    flag. Each channel is silently skipped if not configured/enabled.

    Batched into ONE message per upload instead of one message per finding --
    an upload with 5 new critical clusters previously fired 5 separate
    Discord pings back-to-back, which reads as spam and buries the one thing
    that actually matters (which upload, which app). The batched message
    leads with the app name, review count, and a real clickable link to the
    upload -- "Upload #45" alone told a reader nothing days later.
    """
    if not clusters:
        return

    from app.models.models_supabase import Profile
    from app.models.bulk_models import PushSubscription
    from app.services import notifications

    profile = session.get(Profile, upload.user_id)
    if not profile:
        return

    critical_items = []
    regression_items = []
    for c in clusters:
        if c.regression_detected and c.regression_of_title:
            regression_items.append((c.title, c.regression_of_title, c.regression_confidence or 0.5))
        elif (c.severity or "").lower() == "critical":
            critical_items.append((c.title, c.review_count))

    if not critical_items and not regression_items:
        return

    app_name = (upload.filename or f"Upload #{upload.id}").rsplit(".", 1)[0]
    total = len(critical_items) + len(regression_items)

    if profile.alerts_enabled and profile.alert_webhook_url:
        text = notifications.format_batch_alert(
            app_name, upload.id, upload.total_reviews or 0, critical_items, regression_items
        )
        if await notifications.send_alert(profile.alert_webhook_url, text):
            logger.info(
                f"📣 Sent 1 batched webhook alert ({len(critical_items)} critical, "
                f"{len(regression_items)} regression) for upload {upload.id}"
            )

    if profile.alerts_enabled:
        push_subs = session.exec(
            select(PushSubscription).where(PushSubscription.user_id == upload.user_id)
        ).all()
        if push_subs:
            push_title = f"{total} issue{'s' if total != 1 else ''} in {app_name}"
            push_body = (
                regression_items[0][0] if regression_items and not critical_items
                else critical_items[0][0] if critical_items
                else "New findings ready to review"
            )
            push_url = notifications.upload_link(upload.id)
            sent_push = 0
            for sub in push_subs:
                ok, is_gone = notifications.send_push(
                    {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                    push_title, push_body, url=push_url,
                )
                if ok:
                    sent_push += 1
                elif is_gone:
                    session.delete(sub)
            if sent_push:
                logger.info(f"📱 Sent push notification to {sent_push} device(s) for upload {upload.id}")
            session.commit()

    if profile.email_alerts_enabled and profile.email:
        subject, html = notifications.format_batch_alert_email(
            app_name, upload.id, upload.total_reviews or 0, critical_items, regression_items
        )
        sent, err = await notifications.send_email(profile.email, subject, html)
        if sent:
            logger.info(
                f"📧 Sent 1 batched email alert ({len(critical_items)} critical, "
                f"{len(regression_items)} regression) for upload {upload.id}"
            )
        else:
            logger.warning(f"Email alert failed for upload {upload.id}: {err}")


# Global orchestrator instance (lazy initialization)
_orchestrator: Optional['RealShadowOrchestrator'] = None

# Global set to keep strong references to background tasks (Python 3.12+ requirement)
_background_tasks = set()


def get_shadow_orchestrator():
    """
    Get or create the global shadow orchestrator instance.
    
    Returns:
        RealShadowOrchestrator instance
    """
    global _orchestrator
    
    if _orchestrator is None:
        try:
            # Import here to avoid circular dependencies
            import sys
            from pathlib import Path
            
            # Add backend directory to path
            backend_dir = Path(__file__).parent.parent
            if str(backend_dir) not in sys.path:
                sys.path.insert(0, str(backend_dir))
            
            from shadow_orchestrator_real import RealShadowOrchestrator
            
            _orchestrator = RealShadowOrchestrator(
                output_dir="./shadow_results_production"
            )
            logger.info("✅ Shadow deployment orchestrator initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize shadow orchestrator: {e}", exc_info=True)
            _orchestrator = None
    
    return _orchestrator


async def trigger_shadow_deployment(upload_id: int, csv_path: str):
    """
    Trigger shadow deployment for an upload.
    
    This runs v1 (already processed) + v2 (shadow) + v3 (monitoring) in parallel.
    
    Args:
        upload_id: Upload ID (already processed by v1)
        csv_path: Path to CSV file
    """
    try:
        orchestrator = get_shadow_orchestrator()
        
        if orchestrator is None:
            logger.warning(f"Shadow deployment disabled (orchestrator not available) for upload {upload_id}")
            return
        
        # Check if file exists
        if not Path(csv_path).exists():
            logger.error(f"Shadow deployment skipped: file not found {csv_path}")
            return
        
        logger.info(f"🔄 Starting shadow deployment for upload {upload_id}")
        
        # Run shadow deployment (v1 already done, so we're running v2 + comparison + v3)
        result = await orchestrator.execute_shadow_deployment(csv_path)
        
        # Update the original upload status to completed IMMEDIATELY after v1/v2 complete
        # Don't wait for v3 monitoring to finish
        try:
            from sqlmodel import Session, select
            from app.database.database import engine
            from app.models.bulk_models import Upload, Cluster
            from datetime import datetime
            
            logger.info(f"[DEBUG] Starting upload {upload_id} status update")
            logger.info(f"[DEBUG] v1_metrics.success = {result.v1_metrics.success}")
            
            with Session(engine) as session:
                upload = session.get(Upload, upload_id)
                logger.info(f"[DEBUG] Upload object: {upload}")
                
                if upload and result.v1_metrics.success:
                    # Update upload status and stats
                    upload.status = "completed"
                    upload.completed_at = datetime.utcnow()
                    upload.total_reviews = result.v1_output.get("total_reviews", 0)
                    upload.processed_reviews = result.v1_output.get("kept_reviews", 0)
                    upload.filtered_noise = result.v1_output.get("filtered_reviews", 0)
                    upload.clusters_created = len(result.v1_output.get("clusters", []))
                    upload.processing_time_ms = int(result.v1_metrics.duration_ms)
                    upload.processing_time_seconds = round(result.v1_metrics.duration_ms / 1000, 2)

                    # Add schema detection info if present
                    schema_info = result.v1_output.get("schema_warnings")
                    if schema_info:
                        upload.error_message = f"ℹ️ Schema: {schema_info}"
                        logger.info(f"📋 Schema validation info for upload {upload_id}: {schema_info}")
                    
                    logger.info(f"[DEBUG] About to copy clusters from v1")
                    
                    # Copy clusters from v1's internal upload to user's upload
                    v1_upload_id = result.v1_output.get("upload_id")
                    logger.info(f"[DEBUG] v1_upload_id = {v1_upload_id}")
                    
                    if v1_upload_id:
                        # Get all clusters from v1
                        v1_clusters = list(session.exec(
                            select(Cluster).where(Cluster.upload_id == v1_upload_id)
                        ).all())
                        
                        logger.info(f"[DEBUG] Found {len(v1_clusters)} v1 clusters to copy")
                        
                        # Create duplicate clusters for user's upload
                        for i, v1_cluster in enumerate(v1_clusters):
                            try:
                                user_cluster = Cluster(
                                    cluster_uuid=f"{v1_cluster.cluster_uuid}_user_{upload_id}",  # Make unique
                                    upload_id=upload_id,  # User's upload ID
                                    title=v1_cluster.title,
                                    severity=v1_cluster.severity,
                                    review_count=v1_cluster.review_count,
                                    sample_reviews=v1_cluster.sample_reviews,
                                    status=v1_cluster.status
                                )
                                session.add(user_cluster)
                                logger.info(f"[DEBUG] Added cluster {i+1}/{len(v1_clusters)}")
                            except Exception as cluster_err:
                                logger.error(f"[DEBUG] Failed to add cluster {i}: {cluster_err}")
                        
                        logger.info(f"✅ Copied {len(v1_clusters)} clusters from v1 (upload {v1_upload_id}) to user upload {upload_id}")
                    
                    session.commit()
                    logger.info(f"✅ Updated upload {upload_id} status to completed")

                    # ↩ Fix Verification Loop — detect regressions vs resolved history
                    upload_clusters: List[Cluster] = []
                    try:
                        upload_clusters = list(session.exec(
                            select(Cluster).where(Cluster.upload_id == upload_id)
                        ).all())
                        new_cluster_ids = [c.id for c in upload_clusters if c.id is not None]
                        _detect_regressions(session, new_cluster_ids, upload_id, upload.user_id)
                        session.commit()
                    except Exception as reg_err:
                        logger.warning(f"Regression detection failed (non-fatal): {reg_err}")

                    # 📣 Proactive alerting — regressions and new CRITICAL clusters,
                    # straight to the user's Slack/Discord webhook if they've set one.
                    # Best-effort: never lets a failed/missing webhook affect the upload.
                    try:
                        await _send_upload_alerts(session, upload, upload_clusters)
                    except Exception as alert_err:
                        logger.warning(f"Alert send failed (non-fatal): {alert_err}")

                    # 🗑️ Delete the uploaded CSV — raw data is no longer needed
                    # after clusters have been written to the database.
                    try:
                        Path(csv_path).unlink(missing_ok=True)
                        logger.info(f"🗑️ Deleted CSV for upload {upload_id}: {csv_path}")
                    except Exception as del_err:
                        logger.warning(f"Could not delete CSV {csv_path}: {del_err}")

                    # 🧠 Run pre-generation of 4 severity-category AI explanations.
                    # This runs directly (not as a detached task) because schedule_shadow_deployment
                    # already executes in a background thread with its own event loop — the loop
                    # would be closed before a fire-and-forget task could complete.
                    try:
                        from app.services import explanation_cache
                        from app.services.explanation_pregenerate import pregenerate_for_upload
                        for sev in ("critical", "high", "medium", "low"):
                            explanation_cache.set_status(upload_id, sev, "pending")
                        
                        logger.info(f"🧠 Triggered severity explanation pre-generation for upload {upload_id}")
                        await pregenerate_for_upload(upload_id, engine)
                    except Exception as eg:
                        logger.warning(f"Pre-generation trigger failed (non-fatal): {eg}")

                elif upload:
                    # v1 processing failed — mark the upload as failed instead of
                    # leaving it stuck at "shadow_processing" forever. Previously
                    # this branch only logged a warning and left the status
                    # untouched, so a failed upload would spin in the UI with no
                    # way to know processing had actually stopped.
                    upload.status = "failed"
                    upload.error_message = (
                        (result.v1_metrics.error[:500] if getattr(result.v1_metrics, "error", None) else None)
                        or "Processing failed — please try re-uploading the file."
                    )
                    upload.completed_at = datetime.utcnow()
                    session.commit()
                    logger.warning(
                        f"⚠️ Marked upload {upload_id} as failed (v1_success={result.v1_metrics.success if result else 'No result'})"
                    )
                else:
                    logger.warning(f"[DEBUG] Skipping update: upload not found for id={upload_id}")
        except Exception as e:
            logger.error(f"❌ Failed to update upload {upload_id} status: {e}", exc_info=True)
        
        # Log results
        if result.shadow_success:
            logger.info(
                f"✅ Shadow deployment completed for upload {upload_id}: "
                f"v1={result.v1_metrics.success}, v2={result.v2_metrics.success}, "
                f"match={result.comparison.match_score:.2%}, "
                f"v3_triggered={result.v3_triggered}"
            )
        else:
            logger.warning(
                f"⚠️ Shadow deployment had issues for upload {upload_id}: "
                f"v1={result.v1_metrics.success}, v2={result.v2_metrics.success}"
            )
        
        # Alert on significant differences
        if result.comparison.significant_difference:
            logger.warning(
                f"🚨 ALERT: Significant difference detected for upload {upload_id}! "
                f"Match score: {result.comparison.match_score:.2%}, "
                f"Cluster diff: {result.comparison.cluster_count_diff}, "
                f"v3_alerts={len(result.v3_alerts) if result.v3_alerts else 0}"
            )
    
    except Exception as e:
        logger.error(f"Shadow deployment failed for upload {upload_id}: {e}", exc_info=True)


def schedule_shadow_deployment(upload_id: int, csv_path: str):
    """
    Schedule shadow deployment as a background task.
    
    This is a synchronous wrapper for use in FastAPI background tasks.
    
    Args:
        upload_id: Upload ID
        csv_path: Path to CSV file
    """
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run shadow deployment
        loop.run_until_complete(trigger_shadow_deployment(upload_id, csv_path))
        
        loop.close()
    except Exception as e:
        logger.error(f"Failed to schedule shadow deployment for upload {upload_id}: {e}", exc_info=True)


async def get_shadow_status(upload_id: int) -> Optional[dict]:
    """
    Get shadow deployment status for an upload.
    
    Args:
        upload_id: Upload ID
    
    Returns:
        Shadow deployment status or None if not found
    """
    try:
        orchestrator = get_shadow_orchestrator()
        
        if orchestrator is None:
            return None
        
        # Check if result file exists
        import json
        result_files = list(Path(orchestrator.output_dir).glob(f"shadow_*_{upload_id}.json"))
        
        if not result_files:
            return None
        
        # Read most recent result
        latest_file = max(result_files, key=lambda p: p.stat().st_mtime)
        
        with open(latest_file, 'r') as f:
            result = json.load(f)
        
        return {
            "correlation_id": result.get("correlation_id"),
            "v1_success": result.get("v1_metrics", {}).get("success"),
            "v2_success": result.get("v2_metrics", {}).get("success"),
            "match_score": result.get("comparison", {}).get("match_score"),
            "significant_difference": result.get("comparison", {}).get("significant_difference"),
            "v3_triggered": result.get("v3_triggered"),
            "v3_drift_detected": result.get("v3_drift_detected"),
            "v3_alerts_count": len(result.get("v3_alerts", [])),
            "timestamp": result.get("comparison", {}).get("timestamp")
        }
    
    except Exception as e:
        logger.error(f"Failed to get shadow status for upload {upload_id}: {e}", exc_info=True)
        return None
