"""
Roast API - FastAPI Application (Optimized Bulk Processing Only)
Production-grade async API for processing 100k+ app reviews in <2 minutes.
"""

import logging
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
    
    # Initialize bulk processing API (optimized for 100k+ reviews)
    try:
        from app.bulk_api import init_bulk_api
        init_bulk_api(app)
        logger.info("✅ Bulk processing API initialized")
    except Exception as e:
        logger.error(f"❌ Bulk API initialization failed: {e}")
        raise
    
    yield
    logger.info("🛑 Roast API shutting down...")


app = FastAPI(
    title="Roast API",
    description="Turn brutal user feedback into actionable engineering tickets 🔥 | Optimized for 100k+ reviews",
    version="2.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(auth_router)

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
    return {
        "message": "🔥 Roast API - Turn brutal reviews into engineering tickets",
        "version": "2.0.0",
        "performance": "100k reviews in <60 seconds on CPU",
        "endpoints": {
            "upload": "POST /upload - Upload CSV for bulk processing",
            "status": "GET /uploads/{id}/progress - Check processing status",
            "clusters": "GET /uploads/{id}/clusters - Get results",
            "health": "GET /health - API health check"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "roast-api",
        "version": "2.0.0"
    }
