"""
Bulk review processor with in-memory clustering.
Optimized for processing 100k+ reviews in under 2 minutes on CPU.
"""

import logging
import re
from datetime import datetime
from io import StringIO
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
import pandas as pd
import faiss
from sklearn.neighbors import NearestNeighbors
from sqlmodel import Session, select

from app.bulk_models import BulkJob, Cluster
from app.bulk_embedding import EmbeddingBackend
from app.config import config

logger = logging.getLogger(__name__)


class BulkProcessor:
    """
    High-performance bulk review processor.
    
    Pipeline:
    1. Load CSV
    2. Insert raw reviews into DB
    3. Pre-filter noise (BEFORE embedding)
    4. Batch embed kept reviews (with multiprocessing)
    5. In-memory clustering (no per-review DB queries)
    6. Persist clusters and assignments
    
    Target: 100k reviews in under 2 minutes on CPU.
    """
    
    # Device keywords for metadata extraction (from existing processor)
    DEVICE_KEYWORDS = [
        "pixel", "samsung", "iphone", "galaxy", "oneplus",
        "xiaomi", "huawei", "oppo", "vivo", "realme", "nokia",
        "android", "ios"
    ]
    
    def __init__(self, session: Session, embedding_backend: EmbeddingBackend = None):
        """
        Initialize bulk processor.
        
        Args:
            session: Database session
            embedding_backend: Optional embedding backend (will create if not provided)
        """
        self.session = session
        self.embedding_backend = embedding_backend or EmbeddingBackend()
    
    def process_bulk_job(self, job_id: UUID, csv_path: str) -> Dict:
        """
        Process a bulk job end-to-end.
        
        Args:
            job_id: ID of the BulkJob
            csv_path: Path to CSV file
        
        Returns:
            Stats dict with processing metrics
        """
        logger.info(f"Starting bulk job {job_id} from {csv_path}")
        start_time = datetime.utcnow()
        
        try:
            # Get job
            job = self.session.get(BulkJob, job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")
            
            job.status = "RUNNING"
            self.session.commit()
            
            # Step 0: Load CSV
            logger.info("Step 0: Loading CSV")
            df = self._load_csv(csv_path)
            total_rows = len(df)
            job.total_rows = total_rows
            self.session.commit()
            logger.info(f"Loaded {total_rows} reviews")
            
            # Step 1: Noise filtering (in-memory only, no DB insert)
            logger.info("Step 1: Noise filtering (in-memory)")
            kept_indices = self._prefilter_noise_fast(df)
            kept_count = len(kept_indices)
            job.kept_rows = kept_count
            logger.info(f"Kept {kept_count}/{total_rows} reviews after noise filtering")
            
            # Step 2: Extract kept reviews DataFrame (no DB insert!)
            kept_df = df.iloc[kept_indices].reset_index(drop=True)
            self.session.commit()
            # Extract texts for kept reviews
            kept_texts = kept_df["content"].tolist()
            
            # Step 2: Batch embedding (single-process to avoid crashes)
            logger.info("Step 2: Batch embedding")
            embeddings = self.embedding_backend.encode_batch(
                kept_texts,
                batch_size=config.BATCH_SIZE,
                show_progress=True
            )
            logger.info(f"Generated embeddings: {embeddings.shape}")
            
            # Step 3: In-memory clustering
            logger.info("Step 3: In-memory clustering")
            cluster_assignments = self._cluster_in_memory(embeddings)
            logger.info(f"Created {len(set(cluster_assignments))} clusters")
            
            # Step 4: Persist top priority clusters only (no review inserts!)
            logger.info("Step 4: Persisting top priority clusters to DB")
            self._persist_clusters(
                job_id,
                kept_df,
                cluster_assignments,
                embeddings
            )
            job.cluster_count = len(set(cluster_assignments))
            job.processed_rows = total_rows
            self.session.commit()
            logger.info("Clusters persisted")
            
            # Mark job complete
            job.status = "COMPLETED"
            job.updated_at = datetime.utcnow()
            self.session.commit()
            
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Bulk job {job_id} completed in {elapsed:.2f}s")
            
            return {
                "job_id": str(job_id),
                "status": "COMPLETED",
                "total_rows": total_rows,
                "kept_rows": kept_count,
                "cluster_count": job.cluster_count,
                "elapsed_seconds": elapsed
            }
        
        except Exception as e:
            logger.error(f"Bulk job {job_id} failed: {e}", exc_info=True)
            
            # Mark job as failed
            job = self.session.get(BulkJob, job_id)
            if job:
                job.status = "FAILED"
                job.error_message = str(e)[:500]  # Truncate
                job.updated_at = datetime.utcnow()
                self.session.commit()
            
            raise
    
    def _load_csv(self, csv_path: str) -> pd.DataFrame:
        """
        Load CSV file into DataFrame.
        
        Expected columns (flexible naming):
        - reviewId, userName, content/contents, score, appVersion, etc.
        """
        df = pd.read_csv(csv_path)
        
        # Normalize column names (handle variations)
        column_mapping = {}
        for col in df.columns:
            col_lower = col.lower()
            if col_lower in ["content", "contents", "text", "review"]:
                column_mapping[col] = "content"
            elif col_lower in ["reviewid", "review_id", "id"]:
                column_mapping[col] = "reviewId"
            elif col_lower in ["username", "user_name", "author"]:
                column_mapping[col] = "userName"
            elif col_lower in ["score", "rating", "stars"]:
                column_mapping[col] = "score"
            elif col_lower in ["appversion", "app_version", "version"]:
                column_mapping[col] = "appVersion"
            elif col_lower in ["thumbsupcount", "thumbs_up_count", "likes"]:
                column_mapping[col] = "thumbsUpCount"
        
        if column_mapping:
            df = df.rename(columns=column_mapping)
        
        # Ensure required columns exist
        if "content" not in df.columns:
            raise ValueError("CSV must have a 'content' or 'contents' column")
        
        # Fill defaults
        if "reviewId" not in df.columns:
            df["reviewId"] = df.index.astype(str)
        if "userName" not in df.columns:
            df["userName"] = None
        if "score" not in df.columns:
            df["score"] = 3  # Default neutral
        if "appVersion" not in df.columns:
            df["appVersion"] = None
        if "thumbsUpCount" not in df.columns:
            df["thumbsUpCount"] = 0
        
        # Clean content
        df["content"] = df["content"].fillna("").astype(str).str.strip()
        
        return df
    
    def _prefilter_noise_fast(self, df: pd.DataFrame) -> List[int]:
        """
        Filter noise reviews in-memory (fully vectorized).
        
        Returns only the indices of kept (non-noise) reviews.
        """
        logger.info("Starting noise filter (vectorized, in-memory)...")
        
        # Vectorized operations
        content_lower = df['content'].str.lower()
        content_len = df['content'].str.len()
        
        # Rule 1: Always KEEP low-rated reviews
        keep_low_score = df['score'] <= 3
        
        # Rule 2: Check for negative keywords
        has_negative = pd.Series([False] * len(df), index=df.index)
        for keyword in config.NEGATIVE_KEYWORDS:
            has_negative |= content_lower.str.contains(keyword, regex=False, na=False)
        
        # Rule 3: Check for positive patterns
        has_positive = pd.Series([False] * len(df), index=df.index)
        for pattern in config.POSITIVE_PATTERNS:
            has_positive |= content_lower.str.contains(pattern, regex=False, na=False)
        
        # Rule 4: Short + high rating = noise
        is_short_positive = (
            (content_len < config.MIN_TEXT_LENGTH) & 
            (df['score'] >= config.MIN_SCORE_FOR_NOISE)
        )
        
        # Rule 5: Only positive = noise
        is_only_positive = (
            has_positive & ~has_negative & 
            (df['score'] >= config.MIN_SCORE_FOR_NOISE)
        )
        
        # Keep if: low score OR has negative OR not noise
        keep_mask = keep_low_score | has_negative | ~(is_short_positive | is_only_positive)
        
        kept_indices = df[keep_mask].index.tolist()
        noise_count = len(df) - len(kept_indices)
        
        logger.info(f"Noise filter: {len(kept_indices)} kept, {noise_count} filtered out")
        
        return kept_indices
    
    def _cluster_in_memory(self, embeddings: np.ndarray) -> List[int]:
        """
        Cluster embeddings using FAISS for fast nearest-neighbor search.
        
        Algorithm:
        1. Build FAISS index (inner product for normalized vectors)
        2. For each point, find neighbors within threshold
        3. Group connected components using union-find
        
        Args:
            embeddings: Array of shape [N, D]
        
        Returns:
            List of cluster IDs (length N)
        """
        n, d = embeddings.shape
        
        if n == 0:
            return []
        
        # Normalize embeddings for cosine similarity (required for inner product)
        logger.info("Normalizing embeddings for cosine similarity")
        faiss.normalize_L2(embeddings)  # In-place normalization
        
        # Build FAISS index (IndexFlatIP = flat index with inner product)
        logger.info("Building FAISS index")
        index = faiss.IndexFlatIP(d)  # Inner product (cosine after normalization)
        index.add(embeddings.astype('float32'))
        
        # Search for k nearest neighbors
        k = min(20, n)  # Top 20 neighbors or less
        logger.info(f"Searching for {k} nearest neighbors per point")
        similarities, indices = index.search(embeddings.astype('float32'), k)
        
        # Convert similarity to distance (1 - similarity for cosine)
        distances = 1 - similarities
        
        # Union-find data structure
        parent = list(range(n))
        
        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])  # Path compression
            return parent[x]
        
        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py
        
        # Merge points within threshold
        logger.info(f"Clustering with threshold {config.COSINE_THRESHOLD}")
        for i in range(n):
            for j, dist in zip(indices[i], distances[i]):
                if dist <= config.COSINE_THRESHOLD:
                    union(i, int(j))
        
        # Assign cluster IDs
        cluster_map = {}
        cluster_assignments = []
        next_cluster_id = 0
        
        for i in range(n):
            root = find(i)
            if root not in cluster_map:
                cluster_map[root] = next_cluster_id
                next_cluster_id += 1
            cluster_assignments.append(cluster_map[root])
        
        logger.info(f"Clustering complete: {next_cluster_id} clusters")
        
        return cluster_assignments
    
    def _persist_clusters(
        self,
        job_id: UUID,
        df: pd.DataFrame,
        cluster_assignments: List[int],
        embeddings: np.ndarray
    ):
        """
        Select top 15-20 priority clusters and persist only those (no review DB inserts).
        
        Args:
            job_id: Job ID
            df: DataFrame with kept reviews
            cluster_assignments: Cluster ID for each review
            embeddings: Embeddings array
        """
        from uuid import uuid4
        from collections import defaultdict
        
        # Group reviews by cluster
        clusters_dict = defaultdict(list)
        for i, cluster_id in enumerate(cluster_assignments):
            clusters_dict[cluster_id].append(i)
        
        logger.info(f"Found {len(clusters_dict)} total clusters, selecting top priority clusters...")
        
        # Analyze all clusters and calculate priority scores
        cluster_metadata = []
        
        for cluster_num, review_positions in clusters_dict.items():
            # Get representative review directly from DataFrame
            rep_pos = review_positions[0]
            rep_content = df.iloc[rep_pos]["content"]
            
            # Calculate severity
            severity = self._calculate_severity(rep_content)
            
            # Calculate priority score
            priority_score = self._calculate_priority_score(
                severity=severity,
                cluster_size=len(review_positions),
                content=rep_content
            )
            
            cluster_metadata.append({
                'cluster_num': cluster_num,
                'severity': severity,
                'priority_score': priority_score,
                'review_count': len(review_positions),
                'rep_pos': rep_pos,
                'rep_content': rep_content,
                'review_positions': review_positions
            })
        
        # Sort by priority score (descending)
        cluster_metadata.sort(key=lambda x: x['priority_score'], reverse=True)
        
        # Select top clusters by severity category
        selected_clusters = self._select_top_clusters_by_severity(cluster_metadata, top_n=5)
        
        logger.info(f"Selected {len(selected_clusters)} priority clusters for persistence")
        
        # Persist only selected clusters (no review_id needed!)
        for meta in selected_clusters:
            cluster_uuid = uuid4()
            title = self._generate_title(meta['rep_content'], meta['severity'])
            
            cluster = Cluster(
                id=cluster_uuid,
                job_id=job_id,
                title=title,
                severity=meta['severity'],
                status="freshroast",
                review_count=meta['review_count'],
                sample_review_id=None,  # No review table anymore
                sample_content=meta['rep_content'][:500]  # Store content directly
            )
            self.session.add(cluster)
        
        self.session.flush()
        logger.info(f"Persisted {len(selected_clusters)} priority clusters successfully")
    
    def _calculate_severity(self, text: str) -> str:
        """
        Calculate severity based on keywords (from existing processor logic).
        """
        text_lower = text.lower()
        
        # Critical keywords
        critical_keywords = ["crash", "crashes", "not working", "broken", "unusable"]
        if any(kw in text_lower for kw in critical_keywords):
            return "critical"
        
        # High severity
        high_keywords = ["bug", "error", "issue", "problem", "glitch"]
        if any(kw in text_lower for kw in high_keywords):
            return "high"
        
        # Medium
        medium_keywords = ["slow", "lag", "annoying", "confusing"]
        if any(kw in text_lower for kw in medium_keywords):
            return "medium"
        
        return "low"
    
    def _calculate_priority_score(self, severity: str, cluster_size: int, content: str) -> float:
        """
        Calculate priority score for cluster ranking.
        
        Higher score = higher priority.
        Factors: severity weight + cluster size + keyword importance
        """
        # Severity weights
        severity_weights = {
            'critical': 100,
            'high': 50,
            'medium': 20,
            'low': 5
        }
        severity_score = severity_weights.get(severity, 1)
        
        # Size bonus (log scale to prevent huge clusters from dominating)
        import math
        size_score = math.log10(cluster_size + 1) * 10
        
        # Keyword importance bonus
        content_lower = content.lower()
        critical_keywords = ["crash", "not working", "broken", "unusable", "bug", "error"]
        keyword_bonus = sum(5 for kw in critical_keywords if kw in content_lower)
        
        return severity_score + size_score + keyword_bonus
    
    def _select_top_clusters_by_severity(self, cluster_metadata: list, top_n: int = 5) -> list:
        """
        Select top N clusters from each severity category (high, medium, low).
        
        Args:
            cluster_metadata: List of cluster metadata dicts sorted by priority
            top_n: Number of clusters to select per severity category
        
        Returns:
            List of selected cluster metadata (max 3 * top_n clusters)
        """
        selected = []
        severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        
        for meta in cluster_metadata:
            severity = meta['severity']
            
            # Select top N from each category
            if severity_counts[severity] < top_n:
                selected.append(meta)
                severity_counts[severity] += 1
            
            # Stop when we have top_n from each category or run out
            if all(count >= top_n for count in severity_counts.values()):
                break
        
        logger.info(f"Selected distribution: critical={severity_counts['critical']}, "
                   f"high={severity_counts['high']}, medium={severity_counts['medium']}, "
                   f"low={severity_counts['low']}")
        
        return selected

    
    def _generate_title(self, text: str, severity: str) -> str:
        """
        Generate cluster title (simple version, can be improved with LLM).
        """
        text_lower = text.lower()
        
        # Extract key issue
        if "crash" in text_lower:
            return f"[{severity.upper()}] App crashes"
        elif "login" in text_lower:
            return f"[{severity.upper()}] Login issues"
        elif "slow" in text_lower or "lag" in text_lower:
            return f"[{severity.upper()}] Performance issues"
        elif "subscription" in text_lower or "payment" in text_lower:
            return f"[{severity.upper()}] Payment/subscription issues"
        else:
            # Generic title
            return f"[{severity.upper()}] Issue: {text[:50]}..."
    
    def _extract_version(self, text: str) -> Optional[str]:
        """Extract version from text (e.g., 'v2.4', 'version 3.1')."""
        match = re.search(r'v?(\d+\.\d+(?:\.\d+)?)', text.lower())
        return match.group(0) if match else None
    
    def _extract_device(self, text: str) -> Optional[str]:
        """Extract device from text (e.g., 'Pixel', 'iPhone')."""
        text_lower = text.lower()
        for device in self.DEVICE_KEYWORDS:
            if device in text_lower:
                return device.capitalize()
        return None
