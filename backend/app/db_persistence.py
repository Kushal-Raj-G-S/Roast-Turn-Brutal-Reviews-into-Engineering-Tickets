"""
Database persistence layer for RoastProcessor.
Saves upload records, clusters, and reviews to PostgreSQL.
"""

import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session

from app.models_supabase import Profile, Upload, Cluster, Review
from app.schemas import RoastCluster, RoastReview, Severity, TicketStatus

logger = logging.getLogger(__name__)


class DatabasePersistence:
    """
    Handles saving processor results to PostgreSQL.
    """
    
    def __init__(self, db: Session):
        """
        Initialize with database session.
        
        Args:
            db: SQLAlchemy session
        """
        self.db = db
    
    def create_upload_record(
        self,
        user_id: UUID,
        filename: str,
        file_size_bytes: int,
        total_reviews: int
    ) -> Upload:
        """
        Create initial upload record with PENDING status.
        
        Args:
            user_id: User who uploaded the file
            filename: Name of CSV file
            file_size_bytes: Size of file in bytes
            total_reviews: Total number of reviews in CSV
        
        Returns:
            Upload record
        """
        upload = Upload(
            user_id=user_id,
            filename=filename,
            file_size_bytes=file_size_bytes,
            total_reviews=total_reviews,
            status='pending'
        )
        self.db.add(upload)
        self.db.commit()
        self.db.refresh(upload)
        
        logger.info(f"Created upload record {upload.id} for user {user_id}")
        return upload
    
    def update_upload_status(
        self,
        upload_id: int,
        status: str,
        processed_reviews: Optional[int] = None,
        filtered_noise: Optional[int] = None,
        clusters_created: Optional[int] = None,
        ai_analyzed_count: Optional[int] = None,
        processing_time_ms: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Upload:
        """
        Update upload record with processing results.
        
        Args:
            upload_id: Upload record ID
            status: New status ('processing', 'completed', 'failed')
            processed_reviews: Number of reviews processed
            filtered_noise: Number of reviews filtered as noise
            clusters_created: Number of clusters created
            ai_analyzed_count: Number of clusters AI analyzed
            processing_time_ms: Total processing time
            error_message: Error message if failed
        
        Returns:
            Updated upload record
        """
        upload = self.db.query(Upload).filter(Upload.id == upload_id).first()
        if not upload:
            raise ValueError(f"Upload {upload_id} not found")
        
        upload.status = status
        if processed_reviews is not None:
            upload.processed_reviews = processed_reviews
        if filtered_noise is not None:
            upload.filtered_noise = filtered_noise
        if clusters_created is not None:
            upload.clusters_created = clusters_created
        if ai_analyzed_count is not None:
            upload.ai_analyzed_count = ai_analyzed_count
        if processing_time_ms is not None:
            upload.processing_time_ms = processing_time_ms
        if error_message is not None:
            upload.error_message = error_message
        
        if status == 'completed':
            upload.completed_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(upload)
        
        logger.info(f"Updated upload {upload_id} status to {status}")
        return upload
    
    def save_cluster(
        self,
        upload_id: int,
        cluster: RoastCluster
    ) -> Cluster:
        """
        Save cluster to database.
        
        Args:
            upload_id: Upload record this cluster belongs to
            cluster: RoastCluster from processor
        
        Returns:
            Saved Cluster record
        """
        # Convert severity enum to string
        severity_str = cluster.severity.value if isinstance(cluster.severity, Severity) else str(cluster.severity)
        
        # Convert status enum to string
        status_str = cluster.status.value if isinstance(cluster.status, TicketStatus) else 'fresh_roast'
        
        db_cluster = Cluster(
            upload_id=upload_id,
            cluster_uuid=str(cluster.id),
            title=cluster.title,
            severity=severity_str,
            status=status_str,
            rca_title=cluster.rca_title,
            rca_hypothesis=cluster.rca_hypothesis,
            rca_steps=cluster.rca_steps,
            rca_fix=cluster.rca_fix,
            ai_analyzed=cluster.ai_analyzed,
            affected_versions=getattr(cluster, 'affected_versions', None) or [],
            affected_devices=getattr(cluster, 'affected_devices', None) or [],
            keywords=getattr(cluster, 'keywords', None) or [],
            review_count=len(cluster.evidence) if cluster.evidence else 0
        )
        
        self.db.add(db_cluster)
        self.db.commit()
        self.db.refresh(db_cluster)
        
        logger.debug(f"Saved cluster {db_cluster.id} ({cluster.title})")
        return db_cluster
    
    def save_reviews(
        self,
        cluster_id: int,
        reviews: List[RoastReview]
    ) -> List[Review]:
        """
        Save reviews to database.
        
        Args:
            cluster_id: Database cluster ID
            reviews: List of RoastReview objects
        
        Returns:
            List of saved Review records
        """
        db_reviews = []
        
        for review in reviews:
            db_review = Review(
                cluster_id=cluster_id,
                original_text=review.original_text,
                rating=review.rating,
                version=review.version,
                device=review.device,
                review_date=review.timestamp
            )
            self.db.add(db_review)
            db_reviews.append(db_review)
        
        self.db.commit()
        
        logger.debug(f"Saved {len(db_reviews)} reviews for cluster {cluster_id}")
        return db_reviews
    
    def save_cluster_with_reviews(
        self,
        upload_id: int,
        cluster: RoastCluster
    ) -> Cluster:
        """
        Save cluster and all its reviews in one transaction.
        
        Args:
            upload_id: Upload record ID
            cluster: RoastCluster with evidence
        
        Returns:
            Saved Cluster record with reviews
        """
        # Save cluster
        db_cluster = self.save_cluster(upload_id, cluster)
        
        # Save reviews
        if cluster.evidence:
            self.save_reviews(db_cluster.id, cluster.evidence)
        
        return db_cluster
    
    def get_upload_clusters(self, upload_id: int) -> List[Cluster]:
        """
        Get all clusters for an upload.
        
        Args:
            upload_id: Upload record ID
        
        Returns:
            List of Cluster records
        """
        return self.db.query(Cluster).filter(Cluster.upload_id == upload_id).all()
    
    def get_user_uploads(self, user_id: UUID, limit: int = 10) -> List[Upload]:
        """
        Get recent uploads for a user.
        
        Args:
            user_id: User UUID
            limit: Maximum number of uploads to return
        
        Returns:
            List of Upload records
        """
        return (
            self.db.query(Upload)
            .filter(Upload.user_id == user_id)
            .order_by(Upload.created_at.desc())
            .limit(limit)
            .all()
        )
