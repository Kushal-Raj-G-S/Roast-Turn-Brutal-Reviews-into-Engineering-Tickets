"""
Ranking Strategies for Cluster Prioritization
"""

import logging
from typing import List, Dict, Any
from ...domain.services import IRankingStrategy

logger = logging.getLogger(__name__)


class SeverityBasedRankingStrategy(IRankingStrategy):
    """
    Rank clusters by severity and impact.
    
    Priority Score = 
        severity_weight * severity_score +
        volume_weight * log(review_count) +
        rating_weight * (5 - avg_rating) +
        recency_weight * recency_score
    """

    def __init__(
        self,
        severity_weight: float = 0.4,
        volume_weight: float = 0.3,
        rating_weight: float = 0.2,
        recency_weight: float = 0.1
    ):
        self.severity_weight = severity_weight
        self.volume_weight = volume_weight
        self.rating_weight = rating_weight
        self.recency_weight = recency_weight

    async def rank_clusters(
        self,
        clusters: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Rank clusters by priority."""
        import math
        
        # Calculate priority scores
        for cluster in clusters:
            score = self.calculate_priority_score(cluster)
            cluster['priority_score'] = score
        
        # Sort by priority (descending)
        ranked = sorted(clusters, key=lambda x: x['priority_score'], reverse=True)
        
        logger.info(f"Ranked {len(clusters)} clusters")
        return ranked

    def calculate_priority_score(self, cluster: Dict[str, Any]) -> float:
        """Calculate priority score for a cluster."""
        import math
        
        # Severity score
        severity_map = {
            'critical': 1.0,
            'high': 0.75,
            'medium': 0.5,
            'low': 0.25
        }
        severity_score = severity_map.get(cluster.get('severity', 'low'), 0.25)
        
        # Volume score (logarithmic)
        review_count = cluster.get('review_count', 1)
        volume_score = math.log10(review_count + 1) / 5  # Normalize to 0-1
        
        # Rating score (inverse - lower rating = higher priority)
        avg_rating = cluster.get('avg_rating', 3.0)
        rating_score = (5 - avg_rating) / 5
        
        # Recency score (placeholder - would need timestamps)
        recency_score = 0.5
        
        # Weighted sum
        priority = (
            self.severity_weight * severity_score +
            self.volume_weight * volume_score +
            self.rating_weight * rating_score +
            self.recency_weight * recency_score
        )
        
        return priority
