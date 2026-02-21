"""
Bulk API initialization module.
Sets up database, routes, and background worker.
"""

import logging

from fastapi import FastAPI
from sqlmodel import create_engine

from app.bulk_models import init_db, get_engine
from app.bulk_routes import router as bulk_router, get_db_session
from app.bulk_worker import start_worker, stop_worker
from app.config import config

logger = logging.getLogger(__name__)

# Global engine instance
engine = None


def init_bulk_api(app: FastAPI):
    """
    Initialize bulk processing API.
    
    This should be called during FastAPI startup.
    
    Args:
        app: FastAPI application instance
    """
    global engine
    
    # Create database engine
    logger.info(f"Initializing database: {config.DATABASE_URL}")
    engine = get_engine(config.DATABASE_URL)
    
    # Create tables
    init_db(engine)
    logger.info("Database tables created")
    
    # Ensure upload directory exists
    config.ensure_upload_dir()
    logger.info(f"Upload directory ready: {config.UPLOAD_DIR}")
    
    # Include bulk routes
    app.include_router(bulk_router)
    logger.info("Bulk API routes registered")


def get_engine_instance():
    """Get the global engine instance."""
    return engine
