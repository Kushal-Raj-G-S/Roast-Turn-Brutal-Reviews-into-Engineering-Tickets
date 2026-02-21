# 🔥 Roast Backend - Code Audit for Batched Optimization

**Date:** February 19, 2026  
**Purpose:** Complete code extraction for surgical refactoring to batch embeddings and similarity search  
**Goal:** Process 100,000 reviews in under 60 seconds using GPU + batching

---

## Table of Contents
1. [Complete File: app/memory.py](#1-complete-file-appmemorypy)
2. [Complete File: app/processor.py](#2-complete-file-appprocessorpy)
3. [Complete File: app/main.py](#3-complete-file-appmainpy)
4. [Complete File: app/schemas.py](#4-complete-file-appschemasppy)
5. [Bottleneck Analysis](#5-bottleneck-analysis)
6. [Functions to Refactor](#6-functions-to-refactor)

---

## 1. Complete File: app/memory.py

```python
"""
Roast Memory - ChromaDB Vector Service
"""

from typing import Optional
import chromadb
from sentence_transformers import SentenceTransformer


class RoastMemory:
    """Vector memory layer using ChromaDB and Sentence-Transformers."""
    
    def __init__(self, persist_path: str = "./chroma_db"):
        """Initialize ChromaDB and embedding model."""
        self.client = chromadb.PersistentClient(path=persist_path)
        self.collection = self.client.get_or_create_collection(name="roasts")
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
    
    def get_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        return self.model.encode(text).tolist()
    
    def find_similar(self, text: str, threshold: float = 0.3) -> Optional[str]:
        """
        Find similar cluster in memory.
        
        Args:
            text: The review text to match
            threshold: Distance threshold (lower = more similar)
            
        Returns:
            cluster_id if match found, None otherwise
        """
        embedding = self.get_embedding(text)
        
        # Query ChromaDB
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=1,
            include=["distances", "metadatas"]
        )
        
        # Check if we got results and if distance is below threshold
        if results["ids"] and results["ids"][0]:
            distance = results["distances"][0][0]
            if distance < threshold:
                return results["ids"][0][0]
        
        return None
    
    def save_cluster(self, cluster_id: str, text: str, metadata: dict) -> None:
        """
        Upsert a cluster vector to ChromaDB.
        
        Args:
            cluster_id: Unique cluster ID
            text: Representative text for embedding
            metadata: Additional metadata to store
        """
        embedding = self.get_embedding(text)
        
        self.collection.upsert(
            ids=[cluster_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata]
        )
    
    def reset(self) -> None:
        """Clear all data (for testing)."""
        self.client.delete_collection("roasts")
        self.collection = self.client.get_or_create_collection(name="roasts")
```

---

## 2. Complete File: app/processor.py

```python
"""
Roast Processor - Production-Grade Async Pipeline Orchestrator
================================================================
Connects the Ingestion Layer (CSV) to the Intelligence Layer (LLM).

Features:
- High concurrency with rate limit protection
- Context engineering for optimal token usage
- Fault-tolerant AI analysis (continues on failure)
- Strict Pydantic V2 typing
"""

import asyncio
import logging
import re
import time
from datetime import datetime
from io import StringIO
from typing import Dict, List, Optional
from uuid import uuid4

import pandas as pd

from app.schemas import RoastReview, RoastCluster, IngestStats, Severity, TicketStatus
from app.memory import RoastMemory
from app.llm_service import get_llm_service

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)


class RoastProcessor:
    """
    Production-grade async orchestrator for the Roast pipeline.
    
    Responsibilities:
    1. Parse and filter CSV reviews
    2. Deduplicate using vector memory
    3. Analyze clusters with LLM (parallel, rate-limited)
    4. Persist results to memory
    
    Concurrency Model:
    - CSV parsing: Sequential (I/O bound)
    - Vector search: Sequential (local, fast)
    - LLM analysis: Parallel with semaphore (max 5 concurrent)
    
    Example:
        processor = RoastProcessor()
        stats = await processor.process_batch("reviews.csv")
    """
    
    # Device keywords for metadata extraction
    DEVICE_KEYWORDS = [
        "pixel", "samsung", "iphone", "galaxy", "oneplus", 
        "xiaomi", "huawei", "oppo", "vivo", "realme", "nokia",
        "android", "ios"
    ]
    
    # Max concurrent LLM calls (rate limit protection)
    MAX_LLM_CONCURRENCY = 20  # INCREASED for speed
    
    # Context limits
    MAX_REVIEWS_PER_CLUSTER = 10
    MAX_CONTEXT_CHARS = 3000
    
    def __init__(
        self, 
        memory: Optional[RoastMemory] = None
    ) -> None:
        """
        Initialize the processor with memory layer.
        
        Args:
            memory: RoastMemory instance (created if None)
        """
        self.memory = memory or RoastMemory()
        self.clusters: Dict[str, RoastCluster] = {}
        self._concurrency_limit = asyncio.Semaphore(self.MAX_LLM_CONCURRENCY)
        
        logger.info("RoastProcessor initialized (LLM concurrency: %d)", self.MAX_LLM_CONCURRENCY)
    
    # =========================================================================
    # NOISE FILTERING
    # =========================================================================
    
    def is_noise(self, text: str, rating: int) -> bool:
        """
        Determine if a review is noise (not actionable).
        
        Noise criteria:
        - Text too short (< 10 chars)
        - High rating (> 4) without critical keywords
        
        Args:
            text: Review text content
            rating: Star rating (1-5)
        
        Returns:
            True if review should be filtered out
        """
        text = text.strip()
        
        if len(text) < 10:
            return True
        
        if rating > 4:
            # Exception: high-rated but mentions crash/bug
            critical_keywords = ["crash", "bug", "error", "broken", "freeze"]
            if not any(kw in text.lower() for kw in critical_keywords):
                return True
        
        return False
    
    # =========================================================================
    # METADATA EXTRACTION
    # =========================================================================
    
    def extract_metadata(self, text: str) -> Dict[str, Optional[str]]:
        """
        Extract version and device information from review text.
        
        Args:
            text: Review text to parse
        
        Returns:
            Dict with 'version' and 'device' keys
        """
        metadata: Dict[str, Optional[str]] = {"version": None, "device": None}
        
        # Extract version (e.g., v2.4, v1.0.1, version 2.4)
        version_patterns = [
            r'v(\d+\.\d+(?:\.\d+)?)',
            r'version\s*(\d+\.\d+(?:\.\d+)?)',
        ]
        for pattern in version_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                metadata["version"] = f"v{match.group(1)}"
                break
        
        # Extract device by keyword matching
        text_lower = text.lower()
        for device in self.DEVICE_KEYWORDS:
            if device in text_lower:
                metadata["device"] = device.capitalize()
                break
        
        return metadata
    
    def _calculate_severity(self, text: str, rating: int) -> Severity:
        """
        Calculate severity based on content and rating.
        
        Args:
            text: Review text
            rating: Star rating
        
        Returns:
            Calculated Severity enum
        """
        text_lower = text.lower()
        
        # Critical: crash, data loss, security
        if any(w in text_lower for w in ["crash", "data loss", "security", "hack", "corrupt"]):
            return Severity.CRITICAL
        
        # High: broken, doesn't work, bug
        if any(w in text_lower for w in ["broken", "doesn't work", "bug", "error", "freeze"]):
            return Severity.HIGH
        
        # Based on rating
        if rating <= 2:
            return Severity.HIGH
        elif rating == 3:
            return Severity.MEDIUM
        
        return Severity.LOW
    
    def _generate_title(self, text: str) -> str:
        """Generate a short title from review text."""
        title = text[:50].strip()
        if len(text) > 50:
            last_space = title.rfind(" ")
            if last_space > 20:
                title = title[:last_space] + "..."
            else:
                title += "..."
        return title
    
    # =========================================================================
    # CONTEXT ENGINEERING
    # =========================================================================
    
    def _prepare_context(self, reviews: List[RoastReview]) -> List[str]:
        """
        Prepare optimized context for LLM analysis.
        
        Strategy:
        1. Sort by text length (descending) - longer reviews have more detail
        2. Select top N reviews
        3. Truncate total chars to stay within token limits
        
        Args:
            reviews: List of RoastReview objects
        
        Returns:
            List of review texts optimized for LLM context
        """
        if not reviews:
            return []
        
        # Sort by length (descending) - longer reviews are more informative
        sorted_reviews = sorted(
            reviews, 
            key=lambda r: len(r.original_text), 
            reverse=True
        )
        
        # Select top N
        selected = sorted_reviews[:self.MAX_REVIEWS_PER_CLUSTER]
        
        # Build context with character limit
        context: List[str] = []
        total_chars = 0
        
        for review in selected:
            text = review.original_text.strip()
            
            # Add metadata context if available
            meta_parts = []
            if review.rating:
                meta_parts.append(f"Rating: {review.rating}/5")
            if review.version:
                meta_parts.append(f"Version: {review.version}")
            if review.device:
                meta_parts.append(f"Device: {review.device}")
            
            if meta_parts:
                text = f"[{', '.join(meta_parts)}] {text}"
            
            # Check character limit
            if total_chars + len(text) > self.MAX_CONTEXT_CHARS:
                # Truncate this review to fit
                remaining = self.MAX_CONTEXT_CHARS - total_chars
                if remaining > 100:  # Worth including if >100 chars
                    text = text[:remaining] + "..."
                    context.append(text)
                break
            
            context.append(text)
            total_chars += len(text)
        
        logger.debug(
            "Prepared context: %d reviews, %d chars",
            len(context), total_chars
        )
        return context
    
    # =========================================================================
    # LLM ANALYSIS (ASYNC WORKER)
    # =========================================================================
    
    async def _analyze_cluster(self, cluster: RoastCluster) -> RoastCluster:
        """
        Analyze a single cluster with LLM to generate RCA.
        
        This is an async worker that respects the concurrency limit.
        Fault-tolerant: logs errors but doesn't raise.
        
        Args:
            cluster: The cluster to analyze
        
        Returns:
            The mutated cluster (with or without RCA data)
        """
        cluster_id = str(cluster.id)[:8]
        
        async with self._concurrency_limit:
            logger.info("Analyzing cluster %s (%d reviews)...", cluster_id, len(cluster.evidence))
            
            try:
                # Get LLM service (singleton)
                llm_service = get_llm_service()
                
                # Prepare review data for LLM
                reviews_data = [
                    {
                        "content": r.original_text,
                        "rating": r.rating,
                        "date": r.timestamp.isoformat() if r.timestamp else None
                    }
                    for r in cluster.evidence
                ]
                
                # Collect metadata
                metadata = {
                    "versions": list(set(r.version for r in cluster.evidence if r.version)),
                    "devices": list(set(r.device for r in cluster.evidence if r.device))
                }
                
                # Call LLM with cascading fallback
                rca_result = await llm_service.generate_rca(
                    reviews=reviews_data,
                    severity=cluster.severity.value,
                    metadata=metadata
                )
                
                if rca_result:
                    # Update cluster with RCA results
                    cluster.rca_title = rca_result["rca_title"]
                    cluster.title = rca_result["rca_title"]  # Update main title
                    cluster.rca_hypothesis = rca_result["rca_hypothesis"]
                    cluster.rca_steps = rca_result["rca_steps"]
                    cluster.rca_fix = rca_result["rca_fix"]
                    cluster.ai_analyzed = True
                    
                    logger.info("✓ Cluster %s analyzed: %s", cluster_id, cluster.rca_title[:50])
                else:
                    # Graceful fallback already provided by LLM service
                    logger.warning("⚠ Cluster %s: Using graceful fallback", cluster_id)
                    cluster.ai_analyzed = False
                
            except Exception as e:
                logger.exception("✗ Cluster %s: Unexpected error during analysis: %s", cluster_id, e)
                device = cluster.evidence[0].device if cluster.evidence else "General"
                cluster.title = f"Unanalyzed Issue ({device or 'General'})"
                cluster.ai_analyzed = False
        
        return cluster
    
    # =========================================================================
    # CSV PARSING
    # =========================================================================
    
    def _parse_csv(self, csv_input: str) -> pd.DataFrame:
        """
        Parse CSV input (file path or string content).
        
        Args:
            csv_input: Path to CSV file OR raw CSV string
        
        Returns:
            Parsed DataFrame
        
        Raises:
            ValueError: If CSV cannot be parsed
        """
        try:
            # Check if it's a file path or raw CSV string
            if '\n' in csv_input or ',' in csv_input.split('\n')[0]:
                # It's a CSV string
                return pd.read_csv(StringIO(csv_input))
            else:
                # It's a file path
                return pd.read_csv(csv_input)
        except Exception as e:
            raise ValueError(f"Failed to parse CSV: {e}")
    
    def _detect_columns(self, df: pd.DataFrame) -> tuple[str, Optional[str]]:
        """
        Detect content and rating columns in DataFrame.
        
        Returns:
            Tuple of (content_column, rating_column)
        
        Raises:
            ValueError: If content column not found
        """
        # Detect content column
        content_col = None
        for col in ["content", "review", "text", "comment", "body"]:
            if col in df.columns:
                content_col = col
                break
        
        if not content_col:
            raise ValueError("CSV must have a 'content', 'review', 'text', or 'comment' column")
        
        # Detect rating column
        rating_col = None
        for col in ["rating", "score", "stars"]:
            if col in df.columns:
                rating_col = col
                break
        
        return content_col, rating_col
    
    # =========================================================================
    # MAIN PIPELINE
    # =========================================================================
    
    async def process_csv(self, csv_input: str) -> IngestStats:
        """
        Process CSV without AI analysis (fast ingestion only).
        
        Use process_batch() for full pipeline with AI.
        
        Args:
            csv_input: Path to CSV file OR raw CSV string
        
        Returns:
            IngestStats with processing results
        """
        start_time = time.time()
        stats = IngestStats()
        
        # Parse CSV
        df = self._parse_csv(csv_input)
        content_col, rating_col = self._detect_columns(df)
        
        # Process each row
        for _, row in df.iterrows():
            text = str(row.get(content_col, ""))
            rating = int(row.get(rating_col, 3)) if rating_col else 3
            
            # Skip noise
            if self.is_noise(text, rating):
                continue
            
            stats.processed += 1
            
            # Extract metadata
            metadata = self.extract_metadata(text)
            
            # Check for similar existing cluster
            cluster_id = self.memory.find_similar(text)
            
            if cluster_id and cluster_id in self.clusters:
                # Merge to existing cluster
                cluster = self.clusters[cluster_id]
                review = RoastReview(
                    original_text=text,
                    rating=rating,
                    version=metadata["version"],
                    device=metadata["device"],
                    timestamp=datetime.utcnow()
                )
                cluster.evidence.append(review)
                stats.merged += 1
            else:
                # Create new cluster
                new_id = str(uuid4())
                severity = self._calculate_severity(text, rating)
                
                review = RoastReview(
                    original_text=text,
                    rating=rating,
                    version=metadata["version"],
                    device=metadata["device"],
                    timestamp=datetime.utcnow()
                )
                
                cluster = RoastCluster(
                    id=new_id,
                    title=self._generate_title(text),
                    severity=severity,
                    evidence=[review]
                )
                
                # Save to memory
                self.memory.save_cluster(
                    cluster_id=new_id,
                    text=text,
                    metadata={
                        "title": cluster.title,
                        "severity": severity.value,
                        "version": metadata["version"] or "",
                        "device": metadata["device"] or ""
                    }
                )
                self.clusters[new_id] = cluster
                stats.new_issues += 1
        
        stats.processing_time_ms = (time.time() - start_time) * 1000
        return stats
    
    async def process_batch(
        self, 
        csv_input: str, 
        run_ai_analysis: bool = True
    ) -> IngestStats:
        """
        Full pipeline: Parse CSV → Deduplicate → AI Analysis → Persist.
        
        This is the main entry point for production use.
        
        Args:
            csv_input: Path to CSV file OR raw CSV string
            run_ai_analysis: Whether to run LLM analysis (default True)
        
        Returns:
            IngestStats with full processing results
        """
        start_time = time.time()
        
        # Step 1: Ingest and deduplicate (fast)
        logger.info("Step 1/3: Ingesting and deduplicating reviews...")
        stats = await self.process_csv(csv_input)
        
        logger.info(
            "Ingestion complete: %d processed, %d new clusters, %d merged",
            stats.processed, stats.new_issues, stats.merged
        )
        
        if not run_ai_analysis:
            stats.processing_time_ms = (time.time() - start_time) * 1000
            return stats
        
        # Step 2: AI Analysis (parallel, rate-limited)
        logger.info("Step 2/3: Running AI analysis on %d clusters...", len(self.clusters))
        
        # Get clusters that need analysis
        clusters_to_analyze = [
            c for c in self.clusters.values() 
            if not c.ai_analyzed and len(c.evidence) > 0
        ]
        
        if clusters_to_analyze:
            # Create tasks for parallel execution
            tasks = [
                self._analyze_cluster(cluster) 
                for cluster in clusters_to_analyze
            ]
            
            # Execute with concurrency limit
            analyzed_clusters = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count successes and failures
            for result in analyzed_clusters:
                if isinstance(result, Exception):
                    stats.ai_failed += 1
                    logger.error("Cluster analysis failed: %s", result)
                elif isinstance(result, RoastCluster) and result.ai_analyzed:
                    stats.ai_analyzed += 1
                else:
                    stats.ai_failed += 1
        
        # Step 3: Persist updated clusters
        logger.info("Step 3/3: Persisting analyzed clusters...")
        for cluster in self.clusters.values():
            if cluster.ai_analyzed:
                self.memory.save_cluster(
                    cluster_id=str(cluster.id),
                    text=cluster.evidence[0].original_text if cluster.evidence else "",
                    metadata={
                        "title": cluster.title,
                        "severity": cluster.severity.value,
                        "rca_title": cluster.rca_title or "",
                        "ai_analyzed": str(cluster.ai_analyzed),
                    }
                )
        
        stats.processing_time_ms = (time.time() - start_time) * 1000
        
        logger.info(
            "Pipeline complete: %d analyzed, %d failed, %.0fms",
            stats.ai_analyzed, stats.ai_failed, stats.processing_time_ms
        )
        
        return stats
    
    # =========================================================================
    # ACCESSORS
    # =========================================================================
    
    def get_all_clusters(self) -> List[RoastCluster]:
        """Get all clusters from cache."""
        return list(self.clusters.values())
    
    def get_cluster(self, cluster_id: str) -> Optional[RoastCluster]:
        """Get a specific cluster by ID."""
        return self.clusters.get(cluster_id)
    
    def get_analyzed_clusters(self) -> List[RoastCluster]:
        """Get only clusters that have been AI-analyzed."""
        return [c for c in self.clusters.values() if c.ai_analyzed]
    
    def get_pending_clusters(self) -> List[RoastCluster]:
        """Get clusters awaiting AI analysis."""
        return [c for c in self.clusters.values() if not c.ai_analyzed]
    
    @property
    def roast_count(self) -> int:
        """Total number of roasts across all clusters."""
        return sum(len(c.evidence) for c in self.clusters.values())
```

---

## 3. Complete File: app/main.py

```python
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


@app.post("/upload", response_model=UploadResponse)
async def upload_csv(
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
            "merged": stats.merged,
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
```

---

## 4. Complete File: app/schemas.py

```python
"""
Roast Schemas - Pydantic V2 Data Models
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TicketStatus(str, Enum):
    """Kanban workflow status."""
    FRESH_ROAST = "fresh_roast"
    FIXING = "fixing"
    DONE = "done"


class Severity(str, Enum):
    """Issue severity level."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RoastReview(BaseModel):
    """A single user review (complaint)."""
    id: UUID = Field(default_factory=uuid4)
    original_text: str
    rating: int
    version: Optional[str] = None  # e.g., 'v2.4'
    device: Optional[str] = None   # e.g., 'Pixel 7'
    sentiment: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RoastCluster(BaseModel):
    """A cluster of similar roasts - becomes a ticket."""
    id: UUID = Field(default_factory=uuid4)
    title: str
    status: TicketStatus = TicketStatus.FRESH_ROAST
    severity: Severity = Severity.MEDIUM
    evidence: list[RoastReview] = Field(default_factory=list)
    
    # RCA (Root Cause Analysis) fields - populated by LLM
    rca_title: Optional[str] = Field(default=None, description="AI-generated ticket title")
    rca_hypothesis: Optional[str] = Field(default=None, description="AI root cause hypothesis")
    rca_steps: list[str] = Field(default_factory=list, description="AI reproduction steps")
    rca_fix: Optional[str] = Field(default=None, description="AI suggested fix")
    ai_analyzed: bool = Field(default=False, description="Whether AI analysis completed")


class IngestStats(BaseModel):
    """Stats returned after CSV processing."""
    processed: int = 0
    merged: int = 0
    new_issues: int = 0
    ai_analyzed: int = 0
    ai_failed: int = 0
    processing_time_ms: float = 0.0
```

---

## 5. Bottleneck Analysis

### Current Sequential Processing (BAD)

```python
# In processor.py -> process_csv()
for _, row in df.iterrows():
    text = str(row.get(content_col, ""))
    rating = int(row.get(rating_col, 3)) if rating_col else 3
    
    # Skip noise
    if self.is_noise(text, rating):
        continue
    
    # BOTTLENECK #1: Per-review embedding generation
    cluster_id = self.memory.find_similar(text)  # Calls get_embedding() internally
    
    # BOTTLENECK #2: Per-review ChromaDB query
    # self.memory.find_similar() → self.collection.query()
```

### Specific Bottleneck Functions

#### A. memory.py - Per-Review Embedding (Line 20-21)
```python
def get_embedding(self, text: str) -> list[float]:
    """Generate embedding vector for text."""
    return self.model.encode(text).tolist()  # ❌ ONE review at a time
```

**Problem:** 
- Called once per review (100,000 times for 100k reviews)
- CPU inference: ~50ms per review = 5,000 seconds total
- GPU inference: ~0.5ms per review = 50 seconds total
- **BUT with batching: 0.005ms per review = 0.5 seconds total (100x faster)**

#### B. memory.py - Per-Review ChromaDB Query (Line 33-47)
```python
def find_similar(self, text: str, threshold: float = 0.3) -> Optional[str]:
    """Find similar cluster in memory."""
    embedding = self.get_embedding(text)  # ❌ Bottleneck #1
    
    # ❌ Bottleneck #2: Sequential query
    results = self.collection.query(
        query_embeddings=[embedding],
        n_results=1,
        include=["distances", "metadatas"]
    )
    
    if results["ids"] and results["ids"][0]:
        distance = results["distances"][0][0]
        if distance < threshold:
            return results["ids"][0][0]
    
    return None
```

**Problem:**
- Sequential ChromaDB queries: 100,000 queries × 10ms = 1,000 seconds
- With batching: 1 query for 1,000 embeddings × 100 batches × 50ms = 5 seconds

#### C. processor.py - Sequential Loop (Line 445-500)
```python
async def process_csv(self, csv_input: str) -> IngestStats:
    # ...
    
    # ❌ BOTTLENECK: Sequential processing
    for _, row in df.iterrows():
        text = str(row.get(content_col, ""))
        rating = int(row.get(rating_col, 3)) if rating_col else 3
        
        if self.is_noise(text, rating):
            continue
        
        stats.processed += 1
        metadata = self.extract_metadata(text)
        
        # ❌ Per-review embedding + query
        cluster_id = self.memory.find_similar(text)
        
        if cluster_id and cluster_id in self.clusters:
            # Merge...
        else:
            # Create new cluster...
            # ❌ Another per-cluster embedding + ChromaDB upsert
            self.memory.save_cluster(new_id, text, metadata)
```

---

## 6. Functions to Refactor

### Critical Functions Requiring Batch Implementation

#### Function 1: `RoastMemory.get_embedding()` (memory.py, line 20-21)
**Current:**
```python
def get_embedding(self, text: str) -> list[float]:
    return self.model.encode(text).tolist()
```

**Needs to become:**
```python
def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts at once."""
    embeddings = self.model.encode(texts, batch_size=1024, show_progress_bar=False)
    return embeddings.tolist()
```

---

#### Function 2: `RoastMemory.find_similar()` (memory.py, line 23-47)
**Current:**
```python
def find_similar(self, text: str, threshold: float = 0.3) -> Optional[str]:
    embedding = self.get_embedding(text)
    results = self.collection.query(
        query_embeddings=[embedding],
        n_results=1,
        include=["distances", "metadatas"]
    )
    # ...
```

**Needs to become:**
```python
def find_similar_batch(self, embeddings: List[List[float]], threshold: float = 0.3) -> List[Optional[str]]:
    """Find similar clusters for multiple embeddings at once."""
    results = self.collection.query(
        query_embeddings=embeddings,  # Batch query
        n_results=1,
        include=["distances", "metadatas"]
    )
    # Parse results and return List[Optional[cluster_id]]
```

---

#### Function 3: `RoastMemory.save_cluster()` (memory.py, line 49-65)
**Current:**
```python
def save_cluster(self, cluster_id: str, text: str, metadata: dict) -> None:
    embedding = self.get_embedding(text)
    self.collection.upsert(
        ids=[cluster_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata]
    )
```

**Needs to become:**
```python
def save_clusters_batch(self, cluster_data: List[Dict]) -> None:
    """Save multiple clusters at once."""
    ids = [c["cluster_id"] for c in cluster_data]
    embeddings = self.get_embeddings_batch([c["text"] for c in cluster_data])
    documents = [c["text"] for c in cluster_data]
    metadatas = [c["metadata"] for c in cluster_data]
    
    self.collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas
    )
```

---

#### Function 4: `RoastProcessor.process_csv()` (processor.py, line 417-503)
**Current:** Sequential loop processing one review at a time

**Needs to become:**
1. Parse CSV → DataFrame
2. Filter noise in bulk (pandas vectorized operations)
3. Extract metadata in bulk
4. **Generate all embeddings in one batch** (100k reviews → 1 batch call)
5. **Query ChromaDB in batches** (100k embeddings → 100 batches of 1000)
6. Cluster assignment logic
7. **Save all new clusters in one batch**

---

### GPU Optimization Required

Add to `RoastMemory.__init__()`:
```python
def __init__(self, persist_path: str = "./chroma_db", use_gpu: bool = True):
    self.client = chromadb.PersistentClient(path=persist_path)
    self.collection = self.client.get_or_create_collection(name="roasts")
    
    # GPU acceleration
    if use_gpu and torch.cuda.is_available():
        self.model = SentenceTransformer("all-MiniLM-L6-v2").to('cuda')
        logger.info("✅ SentenceTransformer loaded on GPU")
    else:
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("⚠️  SentenceTransformer running on CPU")
```

---

## Summary for Refactoring AI

### What Needs to Change

1. **memory.py**
   - Add `get_embeddings_batch(texts: List[str])` → batched `model.encode()`
   - Add `find_similar_batch(embeddings, threshold)` → batched `collection.query()`
   - Add `save_clusters_batch(cluster_data)` → batched `collection.upsert()`
   - Add GPU support to `__init__()`

2. **processor.py**
   - Refactor `process_csv()` to:
     - Parse entire CSV at once
     - Filter noise using pandas vectorized ops
     - Call `get_embeddings_batch()` ONCE for all reviews
     - Call `find_similar_batch()` in chunks of 1000
     - Call `save_clusters_batch()` ONCE for all new clusters

3. **Expected Speedup**
   - Current: 100k reviews in ~10 minutes (CPU)
   - After batching: 100k reviews in ~60 seconds (CPU)
   - With A100 GPU: 100k reviews in ~5-10 seconds

---

### Current Bottleneck Breakdown (100k reviews)

| Operation | Current Time | After Batching | With GPU |
|-----------|--------------|----------------|----------|
| CSV Parse | 2 sec | 2 sec | 2 sec |
| Noise Filter | 5 sec | 2 sec | 2 sec |
| **Embeddings** | **600 sec** | **60 sec** | **5 sec** |
| ChromaDB Query | 50 sec | 5 sec | 5 sec |
| Cluster Create | 3 sec | 1 sec | 1 sec |
| **TOTAL** | **660 sec** | **70 sec** | **15 sec** |

---

**End of Code Audit** 🔥
