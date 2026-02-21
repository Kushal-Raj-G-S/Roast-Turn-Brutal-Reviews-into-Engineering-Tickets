"""
Roast API - FastAPI Application
Production-grade async API for processing app reviews into engineering tickets.
"""

import tempfile
from pathlib import Path
from contextlib import asynccontextmanager
import logging
import pandas as pd

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.schemas import IngestStats, RoastCluster
from app.progress_tracker import progress_tracker
from app.schemas_supabase import UploadResponse, ClusterResponse, ClusterDetailResponse
from app.processor import RoastProcessor
from app.database import init_db, get_db
from app.db_persistence import DatabasePersistence
from app.auth_supabase import get_current_user, get_optional_user
from app.models_supabase import Profile, Upload, Cluster

# Import routers
from app.routes.auth_routes_supabase import router as auth_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("roast.api")

# Global processor instance
processor: RoastProcessor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize and cleanup resources."""
    global processor
    logger.info("🔥 Roast API starting up...")
    
    # Initialize database tables
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.warning("⚠️  Continuing without database (some features will be unavailable)")
    
    processor = RoastProcessor()
    logger.info("✅ RoastProcessor initialized")
    
    # Initialize bulk processing API
    try:
        from app.bulk_api import init_bulk_api
        init_bulk_api(app)
        logger.info("✅ Bulk processing API initialized")
    except Exception as e:
        logger.error(f"❌ Bulk API initialization failed: {e}")
        logger.warning("⚠️  Continuing without bulk processing")
    
    yield
    logger.info("🛑 Roast API shutting down...")


app = FastAPI(
    title="Roast API",
    description="Turn brutal user feedback into actionable engineering tickets 🔥",
    version="1.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(auth_router)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "Roast is cooking", "version": "0.2.0"}


@app.post("/test-upload")
async def test_upload_no_auth(file: UploadFile = File(...)):
    """
    Test endpoint - Upload CSV without authentication.
    **FOR TESTING ONLY** - Returns immediate results without database persistence.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")
    
    if processor is None:
        raise HTTPException(status_code=503, detail="Processor not initialized")
    
    tmp_path = None
    try:
        content = await file.read()
        logger.info(f"📥 TEST: Received file: {file.filename} ({len(content)} bytes)")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        # Process the CSV (with AI analysis)
        stats = await processor.process_batch(tmp_path)
        
        # Get clusters with AI results
        clusters = processor.get_all_clusters()
        
        logger.info(
            f"✅ TEST complete: {stats.processed} processed, "
            f"{stats.new_issues} clusters, {stats.ai_analyzed} AI analyzed"
        )
        
        return {
            "success": True,
            "stats": stats.model_dump(),
            "clusters": [
                {
                    "id": str(c.id),
                    "title": c.title,
                    "severity": c.severity.value,
                    "evidence_count": len(c.evidence),
                    "ai_analyzed": c.ai_analyzed,
                    "rca_title": c.rca_title,
                    "rca_hypothesis": c.rca_hypothesis[:200] + "..." if c.rca_hypothesis and len(c.rca_hypothesis) > 200 else c.rca_hypothesis,
                    "rca_fix": c.rca_fix[:200] + "..." if c.rca_fix and len(c.rca_fix) > 200 else c.rca_fix,
                }
                for c in clusters[:20]  # Return first 20 clusters
            ]
        }
        
    except Exception as e:
        logger.exception(f"❌ TEST failed: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


async def process_csv_background(upload_id: int, tmp_path: str, user_id: str):
    """
    Background task to process CSV file.
    Updates progress tracker and database as processing continues.
    """
    from app.database import SessionLocal
    
    db = SessionLocal()
    db_persist = DatabasePersistence(db)
    
    try:
        # Update progress: Starting
        await progress_tracker.update(upload_id, stage="filtering", message="Filtering noise from reviews...")
        
        # Process the CSV
        stats = await processor.process_batch(tmp_path)
        
        # Update progress: Clustering complete
        await progress_tracker.update(
            upload_id,
            stage="saving",
            current=stats.processed,
            message=f"Saving {stats.new_issues} clusters to database..."
        )
        
        # Save clusters to database
        clusters = processor.get_all_clusters()
        for i, cluster in enumerate(clusters, 1):
            db_persist.save_cluster_with_reviews(upload_id, cluster)
            await progress_tracker.update(
                upload_id,
                message=f"Saved cluster {i}/{len(clusters)}"
            )
        
        # Update upload record with results
        db_persist.update_upload_status(
            upload_id=upload_id,
            status='completed',
            processed_reviews=stats.processed,
            filtered_noise=0,
            clusters_created=stats.new_issues,
            ai_analyzed_count=stats.ai_analyzed,
            processing_time_ms=int(stats.processing_time_ms)
        )
        
        # Mark progress as complete
        progress_tracker.complete(
            upload_id,
            success=True,
            message=f"✅ Completed! {stats.new_issues} issues found from {stats.processed} reviews"
        )
        
        logger.info(
            f"✅ Background processing complete for upload {upload_id}: "
            f"{stats.processed} processed, {stats.new_issues} clusters, "
            f"{stats.ai_analyzed} AI analyzed"
        )
        
    except Exception as e:
        logger.exception(f"❌ Background processing failed for upload {upload_id}: {e}")
        db_persist.update_upload_status(
            upload_id, 'failed', error_message=str(e)
        )
        progress_tracker.complete(
            upload_id,
            success=False,
            message=f"❌ Processing failed: {str(e)}"
        )
    finally:
        db.close()
        # Cleanup temp file
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/upload-old", response_model=UploadResponse)
async def upload_csv_old(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a CSV file for processing (requires authentication).
    Returns immediately with upload record. Processing happens in background.
    Use GET /uploads/{id}/progress to check status.
    
    Processes reviews through:
    1. Noise filtering (removes spam, low-quality reviews)
    2. Deduplication (clusters similar issues)
    3. AI Analysis (generates RCA for each cluster)
    4. Persist to PostgreSQL database
    
    Returns Upload record immediately with status='processing'.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")
    
    if processor is None:
        raise HTTPException(status_code=503, detail="Processor not initialized")
    
    # Initialize database persistence
    db_persist = DatabasePersistence(db)
    
    try:
        content = await file.read()
        file_size = len(content)
        logger.info(f"📥 User {user.email} uploaded: {file.filename} ({file_size} bytes)")
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        # Read CSV to count rows
        df = pd.read_csv(tmp_path)
        total_reviews = len(df)
        
        # Create upload record
        upload_record = db_persist.create_upload_record(
            user_id=user.id,
            filename=file.filename,
            file_size_bytes=file_size,
            total_reviews=total_reviews
        )
        
        # Start progress tracking
        progress_tracker.start_tracking(upload_record.id, total_reviews)
        
        # Update status to processing
        db_persist.update_upload_status(upload_record.id, 'processing')
        
        # Schedule background processing
        background_tasks.add_task(
            process_csv_background,
            upload_id=upload_record.id,
            tmp_path=tmp_path,
            user_id=user.id
        )
        
        logger.info(f"✅ Upload {upload_record.id} accepted. Processing in background...")
        
        # Return immediately
        return upload_record
        
    except Exception as e:
        logger.exception(f"❌ Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
        # Cleanup temp file
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


@app.get("/uploads", response_model=list[UploadResponse])
async def get_user_uploads(
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's upload history (requires authentication)."""
    db_persist = DatabasePersistence(db)
    uploads = db_persist.get_user_uploads(user.id, limit=20)
    return uploads


@app.get("/uploads/{upload_id}/progress")
async def get_upload_progress(
    upload_id: int,
    user: Profile = Depends(get_current_user)
):
    """
    Get real-time processing progress for an upload.
    Returns progress percentage, current stage, and status message.
    """
    progress = progress_tracker.get_progress(upload_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Progress not found. Upload may be complete or not started.")
    return progress


@app.get("/uploads/{upload_id}/clusters", response_model=list[ClusterResponse])
async def get_upload_clusters(
    upload_id: int,
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get clusters for a specific upload (requires authentication)."""
    # Verify upload belongs to user
    upload = db.query(Upload).filter(
        Upload.id == upload_id,
        Upload.user_id == user.id
    ).first()
    
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    db_persist = DatabasePersistence(db)
    clusters = db_persist.get_upload_clusters(upload_id)
    return clusters


@app.get("/clusters/{cluster_id}", response_model=ClusterDetailResponse)
async def get_cluster(
    cluster_id: int,
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific cluster by ID (requires authentication)."""
    # Get cluster with upload verification
    cluster = db.query(Cluster).join(Upload).filter(
        Cluster.id == cluster_id,
        Upload.user_id == user.id
    ).first()
    
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    
    return cluster


@app.get("/analytics")
async def get_analytics(
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user analytics and statistics (requires authentication)."""
    from app.models_supabase import UserStatistics, Review
    from sqlalchemy import func
    
    # Get user statistics
    stats = db.query(UserStatistics).filter(
        UserStatistics.user_id == user.id
    ).first()
    
    # Get upload history with timestamps
    uploads = db.query(Upload).filter(
        Upload.user_id == user.id,
        Upload.status == 'completed'
    ).order_by(Upload.created_at.desc()).limit(10).all()
    
    # Get clusters by severity
    clusters_by_severity = db.query(
        Cluster.severity,
        func.count(Cluster.id).label('count')
    ).join(Upload).filter(
        Upload.user_id == user.id
    ).group_by(Cluster.severity).all()
    
    # Get clusters by status
    clusters_by_status = db.query(
        Cluster.status,
        func.count(Cluster.id).label('count')
    ).join(Upload).filter(
        Upload.user_id == user.id
    ).group_by(Cluster.status).all()
    
    # Get recent activity (last 7 uploads with review counts)
    recent_activity = []
    for upload in uploads[:7]:
        review_count = db.query(func.count(Review.id)).join(Cluster).filter(
            Cluster.upload_id == upload.id
        ).scalar()
        recent_activity.append({
            "date": upload.created_at.isoformat() if upload.created_at else None,
            "filename": upload.filename,
            "reviews": review_count or 0,
            "clusters": upload.clusters_created or 0
        })
    
    return {
        "user_statistics": {
            "total_reviews_analyzed": stats.total_reviews_analyzed if stats else 0,
            "total_issues_found": stats.total_issues_found if stats else 0,
            "total_issues_resolved": stats.total_issues_resolved if stats else 0,
            "average_sentiment_score": float(stats.average_sentiment_score) if stats and stats.average_sentiment_score else 0,
            "rating_1_count": stats.rating_1_count if stats else 0,
            "rating_2_count": stats.rating_2_count if stats else 0,
            "rating_3_count": stats.rating_3_count if stats else 0,
            "rating_4_count": stats.rating_4_count if stats else 0,
            "rating_5_count": stats.rating_5_count if stats else 0,
            "average_resolution_time_hours": float(stats.average_resolution_time_hours) if stats and stats.average_resolution_time_hours else 0,
            "last_analysis_at": stats.last_analysis_at.isoformat() if stats and stats.last_analysis_at else None,
        },
        "severity_distribution": {
            "critical": next((c.count for c in clusters_by_severity if c.severity == 'critical'), 0),
            "high": next((c.count for c in clusters_by_severity if c.severity == 'high'), 0),
            "medium": next((c.count for c in clusters_by_severity if c.severity == 'medium'), 0),
            "low": next((c.count for c in clusters_by_severity if c.severity == 'low'), 0),
        },
        "status_distribution": {
            "fresh_roast": next((c.count for c in clusters_by_status if c.status == 'fresh_roast'), 0),
            "assigned": next((c.count for c in clusters_by_status if c.status == 'assigned'), 0),
            "in_progress": next((c.count for c in clusters_by_status if c.status == 'in_progress'), 0),
            "resolved": next((c.count for c in clusters_by_status if c.status == 'resolved'), 0),
            "wont_fix": next((c.count for c in clusters_by_status if c.status == 'wont_fix'), 0),
        },
        "recent_activity": recent_activity,
        "total_uploads": len(uploads)
    }


@app.post("/test/upload")
async def test_upload(
    file: UploadFile = File(...),
):
    """
    Test endpoint for local CSV upload WITHOUT authentication.
    ⚠️  FOR LOCAL TESTING ONLY - NOT FOR PRODUCTION!
    
    Processes CSV and stores in ChromaDB only (not PostgreSQL).
    Use this to test backend accuracy without setting up auth.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")
    
    if processor is None:
        raise HTTPException(status_code=503, detail="Processor not initialized")
    
    try:
        content = await file.read()
        file_size = len(content)
        logger.info(f"📥 TEST UPLOAD: {file.filename} ({file_size} bytes)")
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        # Read CSV to count rows
        df = pd.read_csv(tmp_path)
        total_reviews = len(df)
        logger.info(f"📊 Processing {total_reviews} reviews...")
        
        # Process synchronously for testing
        import time
        start_time = time.time()
        stats = await processor.process_batch(tmp_path)
        processing_time = time.time() - start_time
        
        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)
        
        logger.info(f"✅ Test processing complete in {processing_time:.1f}s")
        
        return {
            "status": "success",
            "filename": file.filename,
            "file_size": file_size,
            "processed": total_reviews,
            "new_issues": stats.new_issues,
            "merged": stats.merged_duplicates,
            "ai_analyzed": stats.ai_analyzed,
            "ai_failed": stats.ai_failed,
            "processing_time_ms": int(processing_time * 1000)
        }
        
    except Exception as e:
        logger.error(f"❌ Test upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
