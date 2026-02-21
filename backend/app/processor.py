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
