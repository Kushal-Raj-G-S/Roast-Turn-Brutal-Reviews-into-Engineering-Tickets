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

from app.bulk_models import Upload, Cluster
from app.bulk_embedding import EmbeddingBackend
from app.config import config

try:
    from app.resource_tracker import ResourceTracker
    RESOURCE_TRACKING_AVAILABLE = True
except ImportError:
    RESOURCE_TRACKING_AVAILABLE = False
    logger.warning("Resource tracking not available (psutil missing)")

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
    
    def __init__(self, session: Session, embedding_backend: EmbeddingBackend = None, version: str = "v1", correlation_id: str = None):
        """
        Initialize bulk processor.
        
        Args:
            session: Database session
            embedding_backend: Optional embedding backend (will create if not provided)
            version: Version identifier (v1, v2, v3) for structured logging
            correlation_id: Correlation ID for tracing execution across versions
        """
        self.session = session
        self.embedding_backend = embedding_backend or EmbeddingBackend()
        self.version = version
        self.correlation_id = correlation_id or str(id(self))[:8]  # Unique ID per instance
        self.schema_warnings = []  # Track schema detection warnings
    
    @property
    def log_prefix(self) -> str:
        """Get structured log prefix for this processor instance."""
        return f"[{self.version}:{self.correlation_id}]"
    
    def process_bulk_job(self, upload_id: int, csv_path: str) -> Dict:
        """
        Process a bulk upload end-to-end.
        
        Args:
            upload_id: ID of the Upload
            csv_path: Path to CSV file
        
        Returns:
            Stats dict with processing metrics
        """
        log_prefix = f"[{self.version}:{self.correlation_id}]"
        logger.info(f"{log_prefix} Starting bulk upload {upload_id} from {csv_path}")
        start_time = datetime.utcnow()
        
        # 🔥 Start resource tracking
        tracker = ResourceTracker() if RESOURCE_TRACKING_AVAILABLE else None
        if tracker:
            tracker.start()
        
        try:
            # Get upload record
            upload = self.session.get(Upload, upload_id)
            if not upload:
                raise ValueError(f"Upload {upload_id} not found")
            
            upload.status = "processing"
            self.session.commit()
            
            # Step 0: Load CSV
            logger.info(f"{log_prefix} Step 0: Loading CSV")
            df = self._load_csv(csv_path)
            total_rows = len(df)
            upload.total_reviews = total_rows
            self.session.commit()
            logger.info(f"{log_prefix} Loaded {total_rows} reviews")
            
            # Step 1: Noise filtering (in-memory only, no DB insert)
            logger.info(f"{log_prefix} Step 1: Noise filtering (in-memory)")
            kept_indices = self._prefilter_noise_fast(df, log_prefix=log_prefix)
            kept_count = len(kept_indices)
            upload.filtered_noise = total_rows - kept_count
            logger.info(f"{log_prefix} Kept {kept_count}/{total_rows} reviews after noise filtering")
            
            # Early exit if all reviews filtered as noise
            if kept_count == 0:
                logger.warning(f"{log_prefix} ⚠️ All reviews filtered as noise. Creating empty result.")
                upload.status = "completed"
                upload.completed_at = datetime.utcnow()
                upload.processing_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                upload.processed_reviews = total_rows
                upload.clusters_created = 0
                upload.error_message = "⚠️ All reviews filtered as low-quality/noise (generic praise, spam, or coordinated content)"
                self.session.commit()
                
                result = {
                    "upload_id": upload_id,
                    "status": "completed",
                    "total_rows": total_rows,
                    "kept_rows": 0,
                    "cluster_count": 0,
                    "elapsed_seconds": (datetime.utcnow() - start_time).total_seconds(),
                    "resources": {}
                }
                
                if self.schema_warnings:
                    result["schema_warnings"] = "; ".join(self.schema_warnings)
                
                return result
            
            # Step 2: Extract kept reviews DataFrame (no DB insert!)
            kept_df = df.iloc[kept_indices].reset_index(drop=True)
            self.session.commit()
            # Extract texts for kept reviews
            kept_texts = kept_df["content"].tolist()
            
            # Step 2: Batch embedding (single-process to avoid crashes)
            logger.info(f"{log_prefix} Step 2: Batch embedding")
            embeddings = self.embedding_backend.encode_batch(
                kept_texts,
                batch_size=config.BATCH_SIZE,
                show_progress=True
            )
            logger.info(f"{log_prefix} Generated embeddings: {embeddings.shape}")
            
            # Step 3: In-memory clustering
            logger.info(f"{log_prefix} Step 3: In-memory clustering")
            cluster_assignments = self._cluster_in_memory(embeddings, log_prefix=log_prefix)
            logger.info(f"{log_prefix} Created {len(set(cluster_assignments))} clusters")
            
            # Step 4: Persist top priority clusters only (no review inserts!)
            logger.info(f"{log_prefix} Step 4: Persisting top priority clusters to DB")
            self._persist_clusters(
                upload_id,
                kept_df,
                cluster_assignments,
                embeddings,
                log_prefix=log_prefix
            )
            upload.clusters_created = len(set(cluster_assignments))
            upload.processed_reviews = total_rows
            self.session.commit()
            logger.info(f"{log_prefix} Clusters persisted")
            
            # Mark upload complete
            upload.status = "completed"
            upload.completed_at = datetime.utcnow()
            upload.processing_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            self.session.commit()
            
            # 🔥 Stop resource tracking and log
            if tracker:
                tracker.stop()
                tracker.log_summary(log_prefix=log_prefix)
            
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Bulk upload {upload_id} completed in {elapsed:.2f}s")
            
            result = {
                "upload_id": upload_id,
                "status": "completed",
                "total_rows": total_rows,
                "kept_rows": kept_count,
                "cluster_count": upload.clusters_created,
                "elapsed_seconds": elapsed,
                "resources": tracker.get_summary() if tracker else {}
            }
            
            # Add schema warnings if any
            if self.schema_warnings:
                result["schema_warnings"] = "; ".join(self.schema_warnings)
            
            return result
        
        except Exception as e:
            logger.error(f"Bulk upload {upload_id} failed: {e}", exc_info=True)
            
            # Mark upload as failed
            upload = self.session.get(Upload, upload_id)
            if upload:
                upload.status = "failed"
                upload.error_message = str(e)[:500]  # Truncate
                upload.completed_at = datetime.utcnow()
                self.session.commit()
            
            raise
    
    def _load_csv(self, csv_path: str) -> pd.DataFrame:
        """
        Load CSV file into DataFrame with intelligent schema detection.
        
        Expected columns (flexible naming):
        - reviewId, userName, content/contents, score, appVersion, etc.
        
        Uses semantic mapping + heuristic fallback for production resilience.
        """
        df = pd.read_csv(csv_path)
        
        # Phase 1: Semantic column mapping (exact matches)
        column_mapping = {}
        content_column_found = False
        
        for col in df.columns:
            col_lower = col.lower().replace("_", "").replace("-", "")
            
            # Comprehensive text column patterns
            if col_lower in ["content", "contents", "text", "review", "reviewtext", 
                            "message", "comment", "feedback", "body", "tweet", 
                            "usercomment", "reviewcontent", "description"]:
                column_mapping[col] = "content"
                content_column_found = True
                if col.lower() != "content":
                    warning = f"Auto-mapped '{col}' → 'content'"
                    logger.info(f"{self.log_prefix} 🔍 Schema detection: {warning}")
                    self.schema_warnings.append(warning)
            elif col_lower in ["reviewid", "review_id", "id"]:
                column_mapping[col] = "reviewId"
            elif col_lower in ["username", "user_name", "author", "user"]:
                column_mapping[col] = "userName"
            elif col_lower in ["score", "rating", "stars", "rate"]:
                column_mapping[col] = "score"
            elif col_lower in ["appversion", "app_version", "version"]:
                column_mapping[col] = "appVersion"
            elif col_lower in ["thumbsupcount", "thumbs_up_count", "likes", "upvotes"]:
                column_mapping[col] = "thumbsUpCount"
        
        if column_mapping:
            df = df.rename(columns=column_mapping)
        
        # Phase 2: Heuristic fallback if no content column detected
        if "content" not in df.columns:
            text_candidates = []
            
            for col in df.columns:
                # Check if column likely contains text (non-numeric, avg length > 20 chars)
                if df[col].dtype == 'object':
                    sample = df[col].dropna().head(100)
                    if len(sample) > 0:
                        avg_length = sample.astype(str).str.len().mean()
                        if avg_length > 20:  # Likely review text
                            text_candidates.append((col, avg_length))
            
            if text_candidates:
                # Choose column with longest average text
                best_col = max(text_candidates, key=lambda x: x[1])
                warning = f"No standard text column found. Auto-mapping '{best_col[0]}' → 'content' (avg: {best_col[1]:.0f} chars)"
                logger.warning(f"{self.log_prefix} ⚠️ Schema detection: {warning}")
                self.schema_warnings.append(warning)
                df = df.rename(columns={best_col[0]: "content"})
                content_column_found = True
        
        # Phase 3: Validation
        if "content" not in df.columns:
            available_cols = ", ".join(df.columns.tolist())
            raise ValueError(
                f"CSV schema validation failed: No text column detected.\n"
                f"Expected columns: content, review, text, message, comment, feedback, body, tweet\n"
                f"Available columns: {available_cols}\n"
                f"Tip: Rename your text column to 'content' or use one of the supported names."
            )
        
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
    
    def _prefilter_noise_fast(self, df: pd.DataFrame, log_prefix: str = "") -> List[int]:
        """
        Filter noise reviews in-memory (fully vectorized).
        
        Returns only the indices of kept (non-noise) reviews.
        """
        logger.info(f"{log_prefix} Starting noise filter (vectorized, in-memory)...")
        
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
        
        logger.info(f"{log_prefix} Noise filter: {len(kept_indices)} kept, {noise_count} filtered out")
        
        return kept_indices
    
    def _cluster_in_memory(self, embeddings: np.ndarray, log_prefix: str = "") -> List[int]:
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
        logger.info(f"{log_prefix} Normalizing embeddings for cosine similarity")
        faiss.normalize_L2(embeddings)  # In-place normalization
        
        # Build FAISS index (IndexFlatIP = flat index with inner product)
        logger.info(f"{log_prefix} Building FAISS index")
        index = faiss.IndexFlatIP(d)  # Inner product (cosine after normalization)
        index.add(embeddings.astype('float32'))
        
        # Search for k nearest neighbors
        k = min(20, n)  # Top 20 neighbors or less
        logger.info(f"{log_prefix} Searching for {k} nearest neighbors per point")
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
        logger.info(f"{log_prefix} Clustering with threshold {config.COSINE_THRESHOLD}")
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
        
        logger.info(f"{log_prefix} Clustering complete: {next_cluster_id} clusters")
        
        return cluster_assignments
    
    def _persist_clusters(
        self,
        upload_id: int,
        df: pd.DataFrame,
        cluster_assignments: List[int],
        embeddings: np.ndarray,
        log_prefix: str = ""
    ):
        """
        Select top 15-20 priority clusters and persist only those (no review DB inserts).
        
        Args:
            upload_id: Upload ID
            df: DataFrame with kept reviews
            cluster_assignments: Cluster ID for each review
            embeddings: Embeddings array
            log_prefix: Logging prefix for traceability
        """
        from uuid import uuid4
        from collections import defaultdict
        
        # Group reviews by cluster
        clusters_dict = defaultdict(list)
        for i, cluster_id in enumerate(cluster_assignments):
            clusters_dict[cluster_id].append(i)
        
        logger.info(f"{log_prefix} Found {len(clusters_dict)} total clusters, selecting top priority clusters...")
        
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
        selected_clusters = self._select_top_clusters_by_severity(cluster_metadata, top_n=5, log_prefix=log_prefix)
        
        logger.info(f"{log_prefix} Selected {len(selected_clusters)} priority clusters for persistence")
        
        # Persist only selected clusters (no review_id needed!)
        for meta in selected_clusters:
            cluster_uuid = str(uuid4())
            title = self._generate_title(meta['rep_content'], meta['severity'])
            
            # Get sample reviews (up to 20) for this cluster
            review_positions = meta['review_positions'][:20]  # Limit to 20
            sample_reviews = []
            for pos in review_positions:
                review_row = df.iloc[pos]
                
                # Helper function to safely get value or None (handles NaN)
                def safe_get(row, key, default=''):
                    val = row.get(key, default)
                    # Check for NaN (pandas NaN values)
                    if pd.isna(val):
                        return None if default == '' else default
                    # Convert empty strings to None for cleaner JSON
                    if val == '':
                        return None
                    return str(val)
                
                sample_reviews.append({
                    'content': str(review_row['content']),
                    'rating': int(review_row.get('score', 0)) if pd.notna(review_row.get('score')) else None,
                    'date': safe_get(review_row, 'at'),
                    'version': safe_get(review_row, 'appVersion'),
                    'device': self._extract_device(review_row['content'])
                })
            
            cluster = Cluster(
                upload_id=upload_id,
                cluster_uuid=cluster_uuid,
                title=title,
                severity=meta['severity'],
                status="fresh_roast",
                review_count=meta['review_count'],
                sample_reviews=sample_reviews
            )
            self.session.add(cluster)
        
        self.session.flush()
        logger.info(f"{log_prefix} Persisted {len(selected_clusters)} priority clusters with sample reviews")
    
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
    
    def _select_top_clusters_by_severity(self, cluster_metadata: list, top_n: int = 5, log_prefix: str = "") -> list:
        """
        Select top N clusters from each severity category (high, medium, low).
        
        Args:
            cluster_metadata: List of cluster metadata dicts sorted by priority
            top_n: Number of clusters to select per severity category
            log_prefix: Logging prefix for traceability
        
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
        
        logger.info(f"{log_prefix} Selected distribution: critical={severity_counts['critical']}, "
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
