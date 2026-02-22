"""
V3 Business Intelligence and Reporting
Automated insights generation and high-impact issue detection.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from collections import Counter
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)


def detect_high_impact_issues(
    results_csv: str,
    clusters_csv: str,
    min_cluster_size: int = 10,
    min_severity_score: float = 0.7
) -> List[Dict]:
    """
    Detect high-impact issues combining volume, severity, and signals.
    
    Args:
        results_csv: Scoring results with V3 signals
        clusters_csv: Clustering results
        min_cluster_size: Minimum cluster size to consider
        min_severity_score: Minimum average score for severity
        
    Returns:
        List of high-impact issue dicts
    """
    df_results = pd.read_csv(results_csv)
    df_clusters = pd.read_csv(clusters_csv)
    
    # Merge results with clusters
    df = pd.merge(
        df_results,
        df_clusters[['review_id', 'cluster_id', 'cluster_label']],
        on='review_id',
        how='left'
    )
    
    # Group by cluster
    cluster_stats = df.groupby('cluster_label').agg({
        'review_id': 'count',  # Volume
        'score': 'mean',        # Severity
        'uncertainty': 'mean',  # Confidence
        'has_retention_signal': 'sum',  # Churn risk
        'has_monetization_complaint': 'sum',  # Revenue impact
        'feature_request_count': 'sum'  # Product opportunities
    }).reset_index()
    
    cluster_stats.columns = [
        'cluster_label', 'volume', 'avg_score', 'avg_uncertainty',
        'retention_signals', 'monetization_complaints', 'feature_requests'
    ]
    
    # Filter by size and severity
    high_impact = cluster_stats[
        (cluster_stats['volume'] >= min_cluster_size) &
        (cluster_stats['avg_score'] >= min_severity_score)
    ].copy()
    
    # Calculate impact score
    high_impact['impact_score'] = (
        high_impact['volume'] * 0.3 +
        high_impact['avg_score'] * 100 * 0.3 +
        high_impact['retention_signals'] * 5 +
        high_impact['monetization_complaints'] * 3 +
        high_impact['feature_requests'] * 2
    )
    
    # Sort by impact
    high_impact = high_impact.sort_values('impact_score', ascending=False)
    
    # Convert to list of dicts
    issues = []
    for _, row in high_impact.iterrows():
        issues.append({
            'cluster_label': row['cluster_label'],
            'volume': int(row['volume']),
            'avg_score': float(row['avg_score']),
            'impact_score': float(row['impact_score']),
            'retention_signals': int(row['retention_signals']),
            'monetization_complaints': int(row['monetization_complaints']),
            'feature_requests': int(row['feature_requests']),
            'severity': 'critical' if row['impact_score'] > 100 else 'high' if row['impact_score'] > 50 else 'medium'
        })
    
    logger.info(f"Detected {len(issues)} high-impact issues")
    return issues


def generate_business_insights(
    results_csv: str,
    clusters_csv: str
) -> Dict[str, any]:
    """
    Generate business-focused insights from review analysis.
    
    Args:
        results_csv: Scoring results
        clusters_csv: Clustering results
        
    Returns:
        Business insights dict
    """
    df_results = pd.read_csv(results_csv)
    df_clusters = pd.read_csv(clusters_csv)
    
    # Overall metrics
    total_reviews = len(df_results)
    actionable_count = df_results['is_actionable'].sum()
    actionable_rate = actionable_count / total_reviews if total_reviews > 0 else 0
    
    # V3 signal analysis
    retention_risk = df_results['has_retention_signal'].sum()
    monetization_issues = df_results['has_monetization_complaint'].sum()
    feature_requests_total = df_results['feature_request_count'].sum()
    mixed_sentiment = df_results['has_concession'].sum()
    
    # Rating distribution
    rating_dist = df_results.groupby('rating')['is_actionable'].agg(['count', 'sum', 'mean']).to_dict('index')
    
    # High-rating issues (critical for reputation)
    high_rating_actionable = df_results[
        (df_results['rating'] >= 4) & (df_results['is_actionable'] == True)
    ]
    
    # Top clusters
    cluster_sizes = df_clusters['cluster_label'].value_counts().head(10)
    top_clusters = [
        {'cluster_label': label, 'count': int(count)}
        for label, count in cluster_sizes.items()
    ]
    
    # Uncertainty analysis
    high_uncertainty = df_results[df_results['uncertainty'] > 0.3]
    
    insights = {
        'summary': {
            'total_reviews': int(total_reviews),
            'actionable_reviews': int(actionable_count),
            'actionable_rate': float(actionable_rate),
            'avg_score': float(df_results['score'].mean()),
            'avg_confidence': float(df_results['confidence'].mean())
        },
        'retention_risk': {
            'count': int(retention_risk),
            'rate': float(retention_risk / total_reviews) if total_reviews > 0 else 0,
            'severity': 'critical' if retention_risk > total_reviews * 0.05 else 'medium' if retention_risk > total_reviews * 0.02 else 'low'
        },
        'monetization': {
            'complaint_count': int(monetization_issues),
            'complaint_rate': float(monetization_issues / total_reviews) if total_reviews > 0 else 0,
            'severity': 'high' if monetization_issues > total_reviews * 0.1 else 'medium' if monetization_issues > total_reviews * 0.05 else 'low'
        },
        'product_opportunities': {
            'feature_requests': int(feature_requests_total),
            'avg_requests_per_review': float(feature_requests_total / total_reviews) if total_reviews > 0 else 0,
            'mixed_sentiment_reviews': int(mixed_sentiment),
            'opportunity_score': float(feature_requests_total * 0.1 + mixed_sentiment * 0.05)
        },
        'reputation_risks': {
            'high_rating_issues_count': len(high_rating_actionable),
            'high_rating_issues_rate': float(len(high_rating_actionable) / len(df_results[df_results['rating'] >= 4])) if len(df_results[df_results['rating'] >= 4]) > 0 else 0,
            'severity': 'critical' if len(high_rating_actionable) > 10 else 'medium' if len(high_rating_actionable) > 5 else 'low'
        },
        'top_clusters': top_clusters,
        'rating_distribution': {
            str(rating): {
                'count': int(stats['count']),
                'actionable': int(stats['sum']),
                'actionable_rate': float(stats['mean'])
            }
            for rating, stats in rating_dist.items()
        },
        'uncertainty': {
            'high_uncertainty_count': len(high_uncertainty),
            'high_uncertainty_rate': float(len(high_uncertainty) / total_reviews) if total_reviews > 0 else 0
        }
    }
    
    return insights


def generate_executive_summary(
    results_csv: str,
    clusters_csv: str,
    output_path: str = 'executive_summary.md'
) -> str:
    """
    Generate executive-friendly summary report in Markdown.
    
    Args:
        results_csv: Scoring results
        clusters_csv: Clustering results
        output_path: Output markdown file path
        
    Returns:
        Markdown content
    """
    # Get insights
    insights = generate_business_insights(results_csv, clusters_csv)
    
    # Get high-impact issues
    issues = detect_high_impact_issues(results_csv, clusters_csv)
    
    # Build markdown report
    md = []
    md.append("# Product Intelligence Executive Summary")
    md.append(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append(f"\n**Analysis Version:** V3.0 (Advanced Signals)")
    md.append("\n---\n")
    
    # Key metrics
    md.append("## 📊 Key Metrics")
    md.append(f"\n- **Total Reviews Analyzed:** {insights['summary']['total_reviews']:,}")
    md.append(f"- **Actionable Issues:** {insights['summary']['actionable_reviews']:,} ({insights['summary']['actionable_rate']:.1%})")
    md.append(f"- **Average Confidence:** {insights['summary']['avg_confidence']:.1%}")
    
    # Critical alerts
    md.append("\n## 🚨 Critical Alerts")
    
    alerts = []
    if insights['retention_risk']['severity'] == 'critical':
        alerts.append(f"- **⚠️ RETENTION RISK:** {insights['retention_risk']['count']} reviews mention uninstalling/leaving ({insights['retention_risk']['rate']:.1%})")
    
    if insights['reputation_risks']['severity'] == 'critical':
        alerts.append(f"- **⚠️ REPUTATION DAMAGE:** {insights['reputation_risks']['high_rating_issues_count']} actionable issues from 4-5 star reviews")
    
    if insights['monetization']['severity'] == 'high':
        alerts.append(f"- **💰 MONETIZATION ISSUES:** {insights['monetization']['complaint_count']} pricing/paywall complaints ({insights['monetization']['complaint_rate']:.1%})")
    
    if alerts:
        md.extend(alerts)
    else:
        md.append("\n✅ No critical alerts detected.")
    
    # High-impact issues
    md.append("\n## 🎯 High-Impact Issues (Top 5)")
    md.append("\n| Issue | Volume | Severity | Retention Risk | Monetization | Priority |")
    md.append("|-------|--------|----------|----------------|--------------|----------|")
    
    for issue in issues[:5]:
        retention_icon = "🔴" if issue['retention_signals'] > 5 else "🟡" if issue['retention_signals'] > 0 else "🟢"
        monetization_icon = "💰" if issue['monetization_complaints'] > 3 else "💵" if issue['monetization_complaints'] > 0 else "-"
        
        md.append(f"| {issue['cluster_label'][:50]} | {issue['volume']} | {issue['avg_score']:.2f} | {retention_icon} {issue['retention_signals']} | {monetization_icon} {issue['monetization_complaints']} | **{issue['severity'].upper()}** |")
    
    # Product opportunities
    md.append("\n## 💡 Product Opportunities")
    md.append(f"\n- **Feature Requests:** {insights['product_opportunities']['feature_requests']} total mentions")
    md.append(f"- **Mixed Sentiment Reviews:** {insights['product_opportunities']['mixed_sentiment_reviews']} (users who like the product but have issues)")
    md.append(f"- **Opportunity Score:** {insights['product_opportunities']['opportunity_score']:.1f}")
    
    # Recommendations
    md.append("\n## ✅ Recommended Actions")
    
    recommendations = []
    
    # Retention
    if insights['retention_risk']['count'] > 0:
        recommendations.append(f"1. **Address Retention Risks:** Immediately investigate {insights['retention_risk']['count']} reviews mentioning uninstall/switching")
    
    # High-rating issues
    if insights['reputation_risks']['high_rating_issues_count'] > 5:
        recommendations.append(f"2. **Fix High-Rating Issues:** Resolve {insights['reputation_risks']['high_rating_issues_count']} issues from satisfied users to prevent churn")
    
    # Top issues
    if len(issues) > 0:
        top_issue = issues[0]
        recommendations.append(f"3. **Prioritize Top Issue:** '{top_issue['cluster_label'][:60]}...' ({top_issue['volume']} reports)")
    
    # Feature requests
    if insights['product_opportunities']['feature_requests'] > 20:
        recommendations.append(f"4. **Product Roadmap:** Review {insights['product_opportunities']['feature_requests']} feature requests for product planning")
    
    if recommendations:
        md.extend(recommendations)
    else:
        md.append("\n✅ System performing well, monitor for emerging patterns.")
    
    # Footer
    md.append("\n---")
    md.append("\n*This report uses AI-powered analysis with probability calibration and uncertainty modeling.*")
    md.append("\n*High-uncertainty predictions are flagged for manual review.*")
    
    # Join and save
    content = "\n".join(md)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"✅ Executive summary saved to {output_path}")
    
    return content


def generate_comprehensive_report(
    results_csv: str,
    clusters_csv: str,
    output_dir: str = './reports'
) -> Dict[str, str]:
    """
    Generate comprehensive multi-format reports.
    
    Args:
        results_csv: Scoring results
        clusters_csv: Clustering results
        output_dir: Output directory for reports
        
    Returns:
        Dict of report paths
    """
    from pathlib import Path
    import json
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    logger.info("Generating comprehensive V3 report...")
    
    # 1. Executive summary (Markdown)
    exec_md = output_path / f"executive_summary_{timestamp}.md"
    generate_executive_summary(results_csv, clusters_csv, str(exec_md))
    
    # 2. Business insights (JSON)
    insights = generate_business_insights(results_csv, clusters_csv)
    insights_json = output_path / f"business_insights_{timestamp}.json"
    with open(insights_json, 'w') as f:
        json.dump(insights, f, indent=2, default=str)
    logger.info(f"Business insights saved to {insights_json}")
    
    # 3. High-impact issues (JSON)
    issues = detect_high_impact_issues(results_csv, clusters_csv)
    issues_json = output_path / f"high_impact_issues_{timestamp}.json"
    with open(issues_json, 'w') as f:
        json.dump(issues, f, indent=2, default=str)
    logger.info(f"High-impact issues saved to {issues_json}")
    
    # 4. CSV exports for deeper analysis
    df_results = pd.read_csv(results_csv)
    
    # Export high-uncertainty for review
    high_uncertainty = df_results[df_results['uncertainty'] > 0.3]
    if len(high_uncertainty) > 0:
        uncertainty_csv = output_path / f"high_uncertainty_{timestamp}.csv"
        high_uncertainty.to_csv(uncertainty_csv, index=False)
        logger.info(f"High-uncertainty reviews saved to {uncertainty_csv}")
    
    # Export retention risks
    retention_risks = df_results[df_results['has_retention_signal'] == True]
    if len(retention_risks) > 0:
        retention_csv = output_path / f"retention_risks_{timestamp}.csv"
        retention_risks.to_csv(retention_csv, index=False)
        logger.info(f"Retention risks saved to {retention_csv}")
    
    # Summary
    print("\n" + "="*80)
    print("V3 COMPREHENSIVE REPORT GENERATED")
    print("="*80)
    print(f"\n📁 Output directory: {output_path}")
    print(f"\n📄 Reports generated:")
    print(f"   1. Executive Summary: {exec_md.name}")
    print(f"   2. Business Insights: {insights_json.name}")
    print(f"   3. High-Impact Issues: {issues_json.name}")
    if len(high_uncertainty) > 0:
        print(f"   4. High-Uncertainty Reviews: uncertainty_csv.name")
    if len(retention_risks) > 0:
        print(f"   5. Retention Risks: {retention_csv.name}")
    print("\n" + "="*80)
    
    return {
        'executive_summary': str(exec_md),
        'business_insights': str(insights_json),
        'high_impact_issues': str(issues_json)
    }
