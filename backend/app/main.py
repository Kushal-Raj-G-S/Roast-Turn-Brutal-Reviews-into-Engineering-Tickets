"""
Roast API - FastAPI Application
Production-grade async API for processing app reviews into engineering tickets.
"""

import tempfile
from pathlib import Path
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import IngestStats, RoastCluster
from app.processor import RoastProcessor

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
    processor = RoastProcessor()
    logger.info("✅ RoastProcessor initialized")
    yield
    logger.info("🛑 Roast API shutting down...")


app = FastAPI(
    title="Roast API",
    description="Turn brutal user feedback into actionable engineering tickets 🔥",
    version="0.2.0",
    lifespan=lifespan
)

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


@app.post("/upload", response_model=IngestStats)
async def upload_csv(file: UploadFile = File(...)):
    """
    Upload a CSV file for processing.
    
    Processes reviews through:
    1. Noise filtering (removes spam, low-quality reviews)
    2. Deduplication (clusters similar issues)
    3. AI Analysis (generates RCA for each cluster)
    
    Returns IngestStats with processing results.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")
    
    if processor is None:
        raise HTTPException(status_code=503, detail="Processor not initialized")
    
    # Save to temp file
    tmp_path = None
    try:
        content = await file.read()
        logger.info(f"📥 Received file: {file.filename} ({len(content)} bytes)")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        # Process the CSV (async with AI analysis)
        stats = await processor.process_batch(tmp_path)
        
        logger.info(
            f"✅ Processing complete: {stats.processed} processed, "
            f"{stats.new_issues} new clusters, {stats.ai_analyzed} AI analyzed"
        )
        
        return stats
        
    except ValueError as e:
        logger.warning(f"⚠️ Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ Processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")
    finally:
        # Cleanup temp file
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


@app.get("/clusters", response_model=list[RoastCluster])
async def get_clusters():
    """Get all roast clusters."""
    if processor is None:
        raise HTTPException(status_code=503, detail="Processor not initialized")
    return processor.get_all_clusters()


@app.get("/clusters/{cluster_id}", response_model=RoastCluster)
async def get_cluster(cluster_id: str):
    """Get a specific cluster by ID."""
    if processor is None:
        raise HTTPException(status_code=503, detail="Processor not initialized")
    cluster = processor.get_cluster(cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return cluster


@app.post("/clusters/{cluster_id}/reanalyze", response_model=RoastCluster)
async def reanalyze_cluster(cluster_id: str):
    """Re-run AI analysis on a specific cluster."""
    if processor is None:
        raise HTTPException(status_code=503, detail="Processor not initialized")
    
    cluster = processor.get_cluster(cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    
    try:
        # Re-run AI analysis
        updated_cluster = await processor._analyze_cluster(cluster)
        # Update in memory
        processor.clusters[cluster_id] = updated_cluster
        logger.info(f"🔄 Re-analyzed cluster {cluster_id}")
        return updated_cluster
    except Exception as e:
        logger.exception(f"❌ Re-analysis failed for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Re-analysis failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
