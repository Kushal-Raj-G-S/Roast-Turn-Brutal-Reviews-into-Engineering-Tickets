"""
Roast API - FastAPI Application (Dual Architecture Support)
Production-grade async API for processing 100k+ app reviews in <2 minutes.

Architecture:
- v1: Legacy optimized pipeline (app/)
- v2: Domain-driven, pluggable architecture (src/)
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers
from app.routes.auth_routes_supabase import router as auth_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("roast.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize and cleanup resources."""
    logger.info("🔥 Roast API starting up...")
    
    # Initialize v1 (legacy) bulk processing API
    try:
        from app.api.bulk_api import init_bulk_api, get_engine_instance
        from app.workers.bulk_worker import start_worker, stop_worker
        
        init_bulk_api(app)
        logger.info("✅ v1 (legacy) bulk processing API initialized")
        
        # Start background worker
        engine = get_engine_instance()
        await start_worker(engine)
        logger.info("✅ v1 background worker started")
    except Exception as e:
        logger.error(f"❌ v1 Bulk API initialization failed: {e}")
        raise
    
    # Initialize v2 (new architecture) if enabled
    use_v2 = os.getenv("ENABLE_V2_ARCHITECTURE", "true").lower() == "true"
    if use_v2:
        try:
            from src.bootstrap import bootstrap_application
            container = bootstrap_application()
            # Store container in app state for access in routes
            app.state.di_container = container
            logger.info("✅ v2 (new architecture) initialized")
        except Exception as e:
            logger.error(f"⚠️ v2 initialization failed (continuing with v1 only): {e}")
    
    yield
    
    logger.info("🛑 Roast API shutting down...")
    stop_worker()


app = FastAPI(
    title="Roast API",
    description="Turn brutal user feedback into actionable engineering tickets 🔥 | Dual Architecture Support",
    version="2.0.0",
    lifespan=lifespan
)

# Include v1 routers (legacy)
app.include_router(auth_router)

# Include v2 routers (new architecture) if enabled
if os.getenv("ENABLE_V2_ARCHITECTURE", "true").lower() == "true":
    try:
        from src.api.routes.upload_v2 import router as upload_v2_router
        app.include_router(upload_v2_router)
        logger.info("✅ v2 routes registered")
    except Exception as e:
        logger.warning(f"⚠️ Failed to register v2 routes: {e}")

# Add feature flag middleware
try:
    from src.api.middleware.feature_flags import ArchitectureRoutingMiddleware
    default_version = os.getenv("DEFAULT_ARCHITECTURE_VERSION", "v1")
    app.add_middleware(ArchitectureRoutingMiddleware, default_version=default_version)
    logger.info(f"✅ Architecture routing middleware added (default: {default_version})")
except Exception as e:
    logger.warning(f"⚠️ Failed to add routing middleware: {e}")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://*.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """API root endpoint."""
    v2_enabled = os.getenv("ENABLE_V2_ARCHITECTURE", "true").lower() == "true"
    
    endpoints = {
        "v1_upload": "POST /upload - Upload CSV (v1 legacy)",
        "v1_status": "GET /uploads/{id}/progress - Check status (v1)",
        "v1_clusters": "GET /uploads/{id}/clusters - Get results (v1)",
        "health": "GET /health - API health check"
    }
    
    if v2_enabled:
        endpoints.update({
            "v2_upload": "POST /api/v2/upload - Upload CSV (v2 new architecture)",
            "v2_status": "GET /api/v2/uploads/{id}/progress - Check status (v2)",
            "v2_clusters": "GET /api/v2/uploads/{id}/clusters - Get results (v2)",
            "v2_health": "GET /api/v2/health - v2 health check"
        })
    
    return {
        "message": "🔥 Roast API - Turn brutal reviews into engineering tickets",
        "version": "2.0.0",
        "architectures": {
            "v1": "Legacy optimized pipeline",
            "v2": "Domain-driven, pluggable architecture" if v2_enabled else "Disabled"
        },
        "performance": "100k reviews in <60 seconds on CPU",
        "endpoints": endpoints
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    v2_enabled = os.getenv("ENABLE_V2_ARCHITECTURE", "true").lower() == "true"
    
    return {
        "status": "healthy",
        "service": "roast-api",
        "version": "2.0.0",
        "architectures": {
            "v1": "active",
            "v2": "active" if v2_enabled else "disabled"
        }
    }

