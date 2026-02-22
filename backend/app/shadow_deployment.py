"""
Shadow Deployment Integration for Production Backend.

Automatically runs v1 (production) + v2 (shadow) + v3 (monitoring) in parallel
on every upload, providing real-time architecture validation.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from app.bulk_models import Upload
from sqlmodel import Session

logger = logging.getLogger(__name__)

# Global orchestrator instance (lazy initialization)
_orchestrator: Optional['RealShadowOrchestrator'] = None


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
            from app.database import engine
            from app.bulk_models import Upload, Cluster
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
                    upload.clusters_created = len(result.v1_output.get("clusters", []))
                    upload.processing_time_ms = int(result.v1_metrics.duration_ms)
                    
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
                else:
                    logger.warning(f"[DEBUG] Skipping update: upload={upload}, v1_success={result.v1_metrics.success if result else 'No result'}")
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
