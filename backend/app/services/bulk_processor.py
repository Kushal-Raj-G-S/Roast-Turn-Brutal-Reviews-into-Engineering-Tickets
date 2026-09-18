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
from sklearn.neighbors import NearestNeighbors
from sqlmodel import Session, select

from app.models.bulk_models import Upload, Cluster
from app.services.bulk_embedding import EmbeddingBackend
from app.core.config import config

try:
    from app.workers.resource_tracker import ResourceTracker
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
            
            # Step 2: Batch embedding (single-process to avoid crashes — see
            # note below, multiprocessing was tried and made things worse).
            # Dedup review text first — the model is deterministic (same
            # input always yields the same vector), and app-store CSV
            # exports are typically full of duplicate reviews ("Good app",
            # emoji spam, copy-paste bot reviews). Normalize case/whitespace
            # before deduping (not just exact-string match): the embedding
            # model's tokenizer is uncased (bert-base-uncased vocab), so
            # "Good app" / "good app" / "GOOD APP " already produce the same
            # embedding — deduping only exact strings was leaving free
            # dedup on the table. Embedding a normalized string once and
            # reusing the vector for every variant is free speed, zero
            # accuracy loss.
            logger.info(f"{log_prefix} Step 2: Batch embedding")
            normalized_texts = [re.sub(r"\s+", " ", t.strip().lower()) for t in kept_texts]
            unique_texts, inverse_indices = np.unique(normalized_texts, return_inverse=True)
            if len(unique_texts) < len(kept_texts):
                dedup_pct = 100 * (1 - len(unique_texts) / len(kept_texts))
                logger.info(
                    f"{log_prefix} Deduplicated {len(kept_texts)} texts -> "
                    f"{len(unique_texts)} unique ({dedup_pct:.1f}% fewer to embed)"
                )
            unique_embeddings = self.embedding_backend.encode_batch(
                unique_texts.tolist(),
                batch_size=config.BATCH_SIZE,
                show_progress=True
            )
            embeddings = unique_embeddings[inverse_indices]
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

            # The session may be left in an unusable state if the failure
            # happened during a flush/commit (e.g. a dropped DB connection) —
            # SQLAlchemy requires an explicit rollback before the session can
            # be used again, otherwise this recovery query itself raises
            # PendingRollbackError and the upload silently never gets marked
            # as failed (it stays stuck at its last in-progress status).
            self.session.rollback()

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
    
    # Clustering shape: ~one cluster per this many reviews, capped, so small
    # uploads stay coarse and large ones get proportionally more granular.
    _REVIEWS_PER_CLUSTER = 150
    _MAX_CLUSTERS = 400

    def _cluster_in_memory(self, embeddings: np.ndarray, log_prefix: str = "") -> List[int]:
        """
        Partition embeddings into K clusters with FAISS KMeans (adaptive K).

        Replaces the previous single-linkage / connected-components approach.
        That one used FAISS only for neighbour search, then merged via
        union-find — which *chained*: on real data a dense core of similar
        reviews all transitively linked into one giant "blob" while the rest
        fell out as singletons. Verified on a 200k upload: ~96% of reviews
        collapsed into ONE cluster at every threshold from 0.70 to 0.92
        similarity — the algorithm, not the threshold, was the problem.

        KMeans partitions into K balanced groups instead — no blob, no
        singleton explosion. K scales with the data (one cluster per ~150
        reviews, capped at 400). Still FAISS (same library as before), and
        fast: ~2s on 50k vectors.
        """
        import faiss  # lazy import — only load when clustering is actually needed
        n, d = embeddings.shape
        if n == 0:
            return []
        if n <= 2:
            return list(range(n))

        emb = embeddings.astype('float32')
        faiss.normalize_L2(emb)  # cosine similarity via inner product

        k = max(1, min(self._MAX_CLUSTERS, n // self._REVIEWS_PER_CLUSTER))
        if k <= 1:
            return [0] * n

        logger.info(f"{log_prefix} FAISS KMeans clustering: {n} vectors -> K={k}")
        km = faiss.Kmeans(d, k, niter=25, seed=42, verbose=False)
        km.train(emb)
        _, labels = km.index.search(emb, 1)
        cluster_assignments = [int(x[0]) for x in labels]
        logger.info(f"{log_prefix} Clustering complete: {len(set(cluster_assignments))} clusters")
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
        
        # Normalized embeddings for cohesion + medoid (representative) picking.
        # Clustering normalized a copy, so the array passed here may not be.
        norm_emb = embeddings.astype('float32')
        _norms = np.linalg.norm(norm_emb, axis=1, keepdims=True)
        _norms[_norms == 0] = 1.0
        norm_emb = norm_emb / _norms

        # Star ratings — the language-agnostic severity signal. Praise is
        # almost always 4-5 stars; real issues 1-3. This is what suppresses
        # "great app!" clusters that English keyword matching lets through,
        # in any language.
        if "score" in df.columns:
            ratings_all = df["score"].fillna(0).astype(float).to_numpy()
        else:
            ratings_all = np.zeros(len(df))

        # Issue-vs-generic reference axis (same embedding space as reviews).
        refs = self._issue_reference_centroids()
        # Guard: issue-specificity dot products (below) require the seed
        # centroids to live in the SAME dimension as the review embeddings.
        # The TF-IDF fallback tier sizes its SVD by sample count, so 10 seeds
        # yield fewer dims than hundreds of reviews (e.g. 9 vs 384) — the
        # matmul would then crash and fail the whole upload. Drop the term
        # instead. (NVIDIA/local tiers share one fixed dim, so this only bites
        # the fallback path.)
        if refs is not None and refs[0].shape[0] != norm_emb.shape[1]:
            logger.warning(
                f"Issue-specificity disabled: seed dim {refs[0].shape[0]} != "
                f"review embedding dim {norm_emb.shape[1]} (embedding fell back "
                f"to a sample-sized tier)"
            )
            refs = None

        # Analyze all clusters and calculate priority scores
        cluster_metadata = []

        for cluster_num, review_positions in clusters_dict.items():
            pos = np.array(review_positions)
            vecs = norm_emb[pos]
            centroid = vecs.mean(axis=0)
            cnorm = np.linalg.norm(centroid) or 1.0
            centroid = centroid / cnorm
            sims = vecs @ centroid
            cohesion = float(sims.mean())                      # cluster tightness 0..1

            # Representative = medoid (closest to centroid), not an arbitrary
            # first row — gives a title/severity that reflects the cluster.
            rep_pos = int(pos[int(np.argmax(sims))])
            rep_content = df.iloc[rep_pos]["content"]

            cl_valid = ratings_all[pos][ratings_all[pos] > 0]
            avg_rating = float(cl_valid.mean()) if cl_valid.size else 0.0

            # Issue-specificity: leans "actionable issue" vs "generic eval".
            # Demotes "good"/"nice"/"ok" clusters rating can't catch. 0 if refs unavailable.
            if refs is not None:
                issue_specificity = float((vecs @ refs[0] - vecs @ refs[1]).mean())
            else:
                issue_specificity = 0.0

            severity = self._calculate_severity(rep_content, avg_rating=avg_rating)
            priority_score = self._calculate_priority_score(
                severity=severity,
                cluster_size=len(review_positions),
                content=rep_content,
                avg_rating=avg_rating,
                cohesion=cohesion,
                issue_specificity=issue_specificity,
            )

            cluster_metadata.append({
                'cluster_num': cluster_num,
                'severity': severity,
                'priority_score': priority_score,
                'review_count': len(review_positions),
                'rep_pos': rep_pos,
                'rep_content': rep_content,
                'review_positions': review_positions,
                'avg_rating': avg_rating,
                'cohesion': cohesion,
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
    
    # Seed phrases defining the "actionable issue" vs "generic evaluation"
    # axis in embedding space. Used to demote clusters of contentless reviews
    # ("good", "nice", "ok" — even when low-rated) that keyword+rating alone
    # can't distinguish from real short issue reports ("app crashes").
    _ISSUE_SEEDS = [
        "the app keeps crashing", "login fails and I can't sign in",
        "it shows an error message", "app freezes and stops responding",
        "payment or subscription problem", "this feature is broken",
        "too many ads interrupting", "very slow and laggy performance",
        "loses my chat history or data", "verification failed cannot access",
    ]
    _GENERIC_SEEDS = [
        "good", "bad", "nice", "worst", "ok", "super", "love it", "amazing",
        "great", "useless", "thank you", "best app", "very good", "awesome",
        "cool", "wow", "excellent", "fine",
    ]

    def _issue_reference_centroids(self):
        """
        (issue_centroid, generic_centroid) in the SAME embedding space as the
        reviews (both embedded via self.embedding_backend). Cached per
        processor. Returns None if embedding the seeds fails — the ranking
        then simply skips the issue-specificity term.
        """
        if getattr(self, "_ref_centroids_cache", "unset") != "unset":
            return self._ref_centroids_cache
        try:
            ie = np.asarray(self.embedding_backend.encode_batch(self._ISSUE_SEEDS), dtype="float32")
            ge = np.asarray(self.embedding_backend.encode_batch(self._GENERIC_SEEDS), dtype="float32")
            def cen(a):
                a = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
                c = a.mean(axis=0)
                return c / (np.linalg.norm(c) or 1.0)
            self._ref_centroids_cache = (cen(ie), cen(ge))
        except Exception as e:
            logger.warning(f"Issue reference centroids unavailable ({e}) — skipping issue-specificity ranking")
            self._ref_centroids_cache = None
        return self._ref_centroids_cache

    def _calculate_severity(self, text: str, avg_rating: float = 0.0) -> str:
        """
        Cluster severity from keywords AND the cluster's average star rating.

        Keywords alone are English-only, so a Hindi/Arabic complaint scored
        "low" and a "great app!!!" praise cluster could both slip through
        mislabelled. The star rating fixes both language-agnostically:
        4-5★ clusters are satisfaction (forced to "low"), 1-2★ clusters are
        real dissatisfaction (floored at "high") even with no English keyword.
        """
        text_lower = text.lower()

        if any(kw in text_lower for kw in ["crash", "crashes", "not working", "broken", "unusable"]):
            kw_sev = "critical"
        elif any(kw in text_lower for kw in ["bug", "error", "issue", "problem", "glitch"]):
            kw_sev = "high"
        elif any(kw in text_lower for kw in ["slow", "lag", "annoying", "confusing"]):
            kw_sev = "medium"
        else:
            kw_sev = "low"

        if not avg_rating or avg_rating <= 0:
            return kw_sev

        order = ["low", "medium", "high", "critical"]
        # Praise: high average stars → not an issue, regardless of keywords.
        if avg_rating >= 3.8:
            return "low"
        # Strongly negative with weak keyword signal (e.g. non-English) → high.
        if avg_rating <= 2.0 and order.index(kw_sev) < order.index("high"):
            return "high"
        if avg_rating <= 2.8 and kw_sev == "low":
            return "medium"
        return kw_sev

    def _calculate_priority_score(
        self,
        severity: str,
        cluster_size: int,
        content: str,
        avg_rating: float = 0.0,
        cohesion: float = 1.0,
        issue_specificity: float = 0.0,
    ) -> float:
        """
        Priority score for ranking clusters. Higher = surfaced first.

        Base = severity weight + log(size) + keyword bonus, then scaled by:
          - a rating factor that strongly demotes praise clusters (4-5★ ->
            ~0.05x, 1★ -> ~1x), so real problems top the list;
          - cohesion (tight, coherent clusters rank above diffuse ones); and
          - issue-specificity: a semantic factor that demotes contentless
            "good"/"nice"/"ok" clusters even when they carry low star ratings,
            which rating and English keywords alone cannot catch.
        """
        severity_weights = {'critical': 100, 'high': 50, 'medium': 20, 'low': 5}
        severity_score = severity_weights.get(severity, 1)

        import math
        size_score = math.log10(cluster_size + 1) * 10

        content_lower = content.lower()
        critical_keywords = ["crash", "not working", "broken", "unusable", "bug", "error"]
        keyword_bonus = sum(5 for kw in critical_keywords if kw in content_lower)

        base = severity_score + size_score + keyword_bonus

        # Rating factor: 1★ -> 1.0, 4★ -> ~0, 5★ -> floored 0.05. Praise sinks.
        if avg_rating and avg_rating > 0:
            rating_factor = max(0.05, min(1.0, (4.0 - avg_rating) / 3.0))
        else:
            rating_factor = 1.0

        cohesion_factor = 0.5 + 0.5 * max(0.0, min(1.0, cohesion))

        # issue_specificity ~ [-0.3, +0.4]: >0 leans issue, <0 leans generic.
        issue_factor = max(0.1, min(1.5, 0.4 + 2.5 * issue_specificity))

        return base * (0.1 + rating_factor) * cohesion_factor * issue_factor
    
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
