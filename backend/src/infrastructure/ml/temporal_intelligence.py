"""
Temporal Intelligence Module for V3
Compare clusters over time, detect new issues, track growth/spikes.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Set
from collections import Counter
import logging

logger = logging.getLogger(__name__)


def compare_cluster_results(
    old_clusters_csv: str,
    new_clusters_csv: str,
    min_cluster_size: int = 5
) -> Dict[str, any]:
    """
    Compare clustering results between two time periods.
    
    Args:
        old_clusters_csv: Older clustering results (with 'cluster_id', 'text', 'cluster_label')
        new_clusters_csv: Newer clustering results
        min_cluster_size: Minimum cluster size to consider
        
    Returns:
        Comparison analysis dict
    """
    logger.info(f"Loading old clusters: {old_clusters_csv}")
    df_old = pd.read_csv(old_clusters_csv)
    
    logger.info(f"Loading new clusters: {new_clusters_csv}")
    df_new = pd.read_csv(new_clusters_csv)
    
    # Get cluster statistics
    old_clusters = df_old.groupby('cluster_label').size()
    new_clusters = df_new.groupby('cluster_label').size()
    
    # Filter by minimum size
    old_clusters = old_clusters[old_clusters >= min_cluster_size]
    new_clusters = new_clusters[new_clusters >= min_cluster_size]
    
    # Identify new, growing, shrinking clusters
    old_labels = set(old_clusters.index)
    new_labels = set(new_clusters.index)
    
    # New clusters
    new_cluster_labels = new_labels - old_labels
    
    # Common clusters
    common_labels = old_labels & new_labels
    
    # Growth/shrinkage
    growth_data = []
    for label in common_labels:
        old_size = old_clusters[label]
        new_size = new_clusters[label]
        growth_pct = (new_size - old_size) / old_size * 100
        
        growth_data.append({
            'cluster_label': label,
            'old_size': int(old_size),
            'new_size': int(new_size),
            'growth_pct': float(growth_pct),
            'growth_abs': int(new_size - old_size)
        })
    
    growth_df = pd.DataFrame(growth_data)
    
    # Detect spikes (>50% growth and significant absolute increase)
    if len(growth_df) > 0:
        spikes = growth_df[
            (growth_df['growth_pct'] > 50) & 
            (growth_df['growth_abs'] > 10)
        ].sort_values('growth_pct', ascending=False)
    else:
        spikes = pd.DataFrame()
    
    # Top growing clusters
    if len(growth_df) > 0:
        top_growing = growth_df.nlargest(5, 'growth_pct')
    else:
        top_growing = pd.DataFrame()
    
    analysis = {
        'old_cluster_count': len(old_labels),
        'new_cluster_count': len(new_labels),
        'new_clusters': list(new_cluster_labels),
        'disappeared_clusters': list(old_labels - new_labels),
        'common_clusters': len(common_labels),
        'spike_count': len(spikes),
        'spikes': spikes.to_dict('records') if len(spikes) > 0 else [],
        'top_growing': top_growing.to_dict('records') if len(top_growing) > 0 else []
    }
    
    logger.info("Cluster Comparison:")
    logger.info(f"  Old: {len(old_labels)} clusters, New: {len(new_labels)} clusters")
    logger.info(f"  New clusters detected: {len(new_cluster_labels)}")
    logger.info(f"  Spikes detected: {len(spikes)}")
    
    return analysis


def detect_new_issues(
    old_clusters_csv: str,
    new_clusters_csv: str,
    similarity_threshold: float = 0.6
) -> List[Dict]:
    """
    Detect genuinely new issue clusters (not just renamed).
    
    Args:
        old_clusters_csv: Older clustering results
        new_clusters_csv: Newer clustering results
        similarity_threshold: Minimum similarity to consider "same" cluster
        
    Returns:
        List of new issue dicts
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    
    df_old = pd.read_csv(old_clusters_csv)
    df_new = pd.read_csv(new_clusters_csv)
    
    # Get cluster labels (centroids)
    old_labels = df_old.groupby('cluster_label')['cluster_label'].first().values
    new_labels = df_new.groupby('cluster_label')['cluster_label'].first().values
    
    if len(old_labels) == 0 or len(new_labels) == 0:
        return []
    
    # Compute TF-IDF similarity between cluster labels
    all_labels = list(old_labels) + list(new_labels)
    vectorizer = TfidfVectorizer(max_features=50)
    tfidf = vectorizer.fit_transform(all_labels)
    
    old_tfidf = tfidf[:len(old_labels)]
    new_tfidf = tfidf[len(old_labels):]
    
    # Compute similarity matrix
    similarity = cosine_similarity(new_tfidf, old_tfidf)
    
    # Find new clusters (low similarity to all old clusters)
    new_issues = []
    for i, new_label in enumerate(new_labels):
        max_similarity = similarity[i].max()
        
        if max_similarity < similarity_threshold:
            # Genuinely new issue
            cluster_size = (df_new['cluster_label'] == new_label).sum()
            
            new_issues.append({
                'cluster_label': new_label,
                'size': int(cluster_size),
                'max_similarity_to_old': float(max_similarity),
                'is_new': True
            })
    
    logger.info(f"Detected {len(new_issues)} genuinely new issues")
    return new_issues


def compute_trend_score(
    results_csv: str,
    time_column: str = 'at',
    window_days: int = 7
) -> Dict[str, float]:
    """
    Compute trend scores for key metrics over time.
    
    Args:
        results_csv: Results with timestamps
        time_column: Name of timestamp column
        window_days: Rolling window size in days
        
    Returns:
        Trend scores dict
    """
    df = pd.read_csv(results_csv)
    
    if time_column not in df.columns:
        logger.warning(f"No {time_column} column found, cannot compute trends")
        return {}
    
    # Convert to datetime
    df[time_column] = pd.to_datetime(df[time_column], errors='coerce')
    df = df.dropna(subset=[time_column])
    
    if len(df) == 0:
        return {}
    
    # Sort by time
    df = df.sort_values(time_column)
    
    # Compute daily aggregates
    df['date'] = df[time_column].dt.date
    daily = df.groupby('date').agg({
        'is_actionable': 'mean',  # Actionability rate
        'uncertainty': 'mean',     # Uncertainty level
        'score': 'mean'            # Average score
    }).reset_index()
    
    if len(daily) < 2:
        return {}
    
    # Compute trends (linear regression slope)
    from sklearn.linear_model import LinearRegression
    
    X = np.arange(len(daily)).reshape(-1, 1)
    
    trends = {}
    
    # Actionability trend
    y_actionable = daily['is_actionable'].values
    lr_actionable = LinearRegression().fit(X, y_actionable)
    trends['actionability_trend'] = float(lr_actionable.coef_[0])
    
    # Uncertainty trend
    if 'uncertainty' in daily.columns:
        y_uncertainty = daily['uncertainty'].values
        lr_uncertainty = LinearRegression().fit(X, y_uncertainty)
        trends['uncertainty_trend'] = float(lr_uncertainty.coef_[0])
    
    # Score trend
    y_score = daily['score'].values
    lr_score = LinearRegression().fit(X, y_score)
    trends['score_trend'] = float(lr_score.coef_[0])
    
    # Recent vs baseline comparison
    recent_days = min(window_days, len(daily) // 2)
    recent = daily.tail(recent_days)
    baseline = daily.head(recent_days)
    
    trends['actionable_recent_vs_baseline'] = float(
        recent['is_actionable'].mean() - baseline['is_actionable'].mean()
    )
    
    logger.info("Trend Analysis:")
    logger.info(f"  Actionability trend: {trends['actionability_trend']:.4f}/day")
    logger.info(f"  Recent vs baseline: {trends['actionable_recent_vs_baseline']:+.2%}")
    
    return trends


def generate_temporal_report(
    old_clusters_csv: str,
    new_clusters_csv: str,
    old_results_csv: str,
    new_results_csv: str,
    output_path: str = 'temporal_intelligence_report.json'
) -> Dict[str, any]:
    """
    Generate comprehensive temporal intelligence report.
    
    Args:
        old_clusters_csv: Old clustering results
        new_clusters_csv: New clustering results
        old_results_csv: Old scoring results
        new_results_csv: New scoring results
        output_path: Output JSON path
        
    Returns:
        Complete temporal report
    """
    import json
    
    logger.info("Generating temporal intelligence report...")
    
    # Cluster comparison
    cluster_comparison = compare_cluster_results(old_clusters_csv, new_clusters_csv)
    
    # New issue detection
    new_issues = detect_new_issues(old_clusters_csv, new_clusters_csv)
    
    # Trend analysis
    trends = compute_trend_score(new_results_csv)
    
    # Volume comparison
    df_old = pd.read_csv(old_results_csv)
    df_new = pd.read_csv(new_results_csv)
    
    volume_change = {
        'old_volume': len(df_old),
        'new_volume': len(df_new),
        'volume_change_pct': float((len(df_new) - len(df_old)) / len(df_old) * 100),
        'old_actionable': int(df_old['is_actionable'].sum()),
        'new_actionable': int(df_new['is_actionable'].sum()),
        'actionable_change_pct': float(
            (df_new['is_actionable'].sum() - df_old['is_actionable'].sum()) / 
            df_old['is_actionable'].sum() * 100
        )
    }
    
    # Assemble report
    report = {
        'cluster_comparison': cluster_comparison,
        'new_issues': new_issues,
        'trends': trends,
        'volume_change': volume_change,
        'analysis_timestamp': pd.Timestamp.now().isoformat()
    }
    
    # Save
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    logger.info(f"✅ Temporal intelligence report saved to {output_path}")
    
    # Print summary
    print("\n" + "="*80)
    print("TEMPORAL INTELLIGENCE REPORT")
    print("="*80)
    
    print(f"\n📊 Volume Changes:")
    print(f"  Reviews: {volume_change['old_volume']} → {volume_change['new_volume']} ({volume_change['volume_change_pct']:+.1f}%)")
    print(f"  Actionable: {volume_change['old_actionable']} → {volume_change['new_actionable']} ({volume_change['actionable_change_pct']:+.1f}%)")
    
    print(f"\n🔍 Cluster Evolution:")
    print(f"  Clusters: {cluster_comparison['old_cluster_count']} → {cluster_comparison['new_cluster_count']}")
    print(f"  New clusters: {len(cluster_comparison['new_clusters'])}")
    print(f"  Spikes detected: {cluster_comparison['spike_count']}")
    
    if cluster_comparison['spikes']:
        print(f"\n⚠️  Top Spikes:")
        for spike in cluster_comparison['spikes'][:3]:
            print(f"    - {spike['cluster_label']}: {spike['old_size']} → {spike['new_size']} (+{spike['growth_pct']:.1f}%)")
    
    if new_issues:
        print(f"\n🆕 New Issues Detected: {len(new_issues)}")
        for issue in new_issues[:5]:
            print(f"    - {issue['cluster_label']} (size: {issue['size']})")
    
    if trends:
        print(f"\n📈 Trends:")
        print(f"  Actionability: {trends['actionability_trend']:+.4f}/day")
        print(f"  Recent vs baseline: {trends['actionable_recent_vs_baseline']:+.2%}")
    
    print("\n" + "="*80)
    
    return report
