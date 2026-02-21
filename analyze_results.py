"""
Results Analyzer - Examine backend predictions and clustering quality
"""
import requests
import json
from collections import Counter
from datetime import datetime

BACKEND_URL = "http://localhost:8000"

def analyze_clusters():
    """Fetch and analyze all clusters from backend"""
    
    print("\n" + "="*80)
    print("  📊 ROAST - Clustering Results Analysis")
    print("="*80)
    
    try:
        response = requests.get(f"{BACKEND_URL}/clusters", timeout=10)
        clusters = response.json()
    except Exception as e:
        print(f"\n❌ Error: Cannot connect to backend!")
        print(f"   Make sure backend is running on {BACKEND_URL}")
        return
    
    if not clusters:
        print("\n⚠️  No clusters found! Upload a test dataset first:")
        print("   → Open http://localhost:3000/upload")
        print("   → Upload test_100_reviews.csv")
        return
    
    print(f"\n📈 Total Clusters: {len(clusters)}")
    print("="*80 + "\n")
    
    # Overall stats
    severities = Counter(c.get('severity', 'unknown') for c in clusters)
    total_reviews = sum(len(c.get('review_ids', [])) for c in clusters)
    with_rca = sum(1 for c in clusters if c.get('root_cause_analysis'))
    
    print("📊 OVERALL STATISTICS")
    print("-" * 80)
    print(f"  Total Reviews Clustered: {total_reviews:,}")
    print(f"  Clusters with RCA: {with_rca}/{len(clusters)} ({with_rca/len(clusters)*100:.1f}%)")
    print(f"\n  Severity Distribution:")
    for severity in ['critical', 'high', 'medium', 'low']:
        count = severities.get(severity, 0)
        pct = count / len(clusters) * 100 if clusters else 0
        bar = "█" * int(pct / 2)
        print(f"    {severity.upper():8} | {bar:50} {count:3} ({pct:5.1f}%)")
    
    # Top issues by evidence
    print("\n\n🔥 TOP 10 ISSUES BY EVIDENCE COUNT")
    print("-" * 80)
    sorted_clusters = sorted(clusters, key=lambda c: len(c.get('review_ids', [])), reverse=True)
    
    for i, cluster in enumerate(sorted_clusters[:10], 1):
        review_count = len(cluster.get('review_ids', []))
        severity = cluster.get('severity', 'unknown')
        title = cluster.get('title', 'Unknown Issue')
        
        # Severity emoji
        emoji = {
            'critical': '🔴',
            'high': '🟠',
            'medium': '🟡',
            'low': '🟢'
        }.get(severity, '⚪')
        
        print(f"\n{i:2}. {emoji} {title[:70]}")
        print(f"    Evidence: {review_count} reviews | Severity: {severity.upper()}")
        
        # RCA summary
        rca = cluster.get('root_cause_analysis', {})
        if rca:
            rca_title = rca.get('title', 'N/A')
            hypothesis = rca.get('hypothesis', 'N/A')
            print(f"    RCA: {rca_title}")
            print(f"    Cause: {hypothesis[:100]}...")
        else:
            print(f"    RCA: ❌ Not generated")
    
    # Clustering quality metrics
    print("\n\n✅ CLUSTERING QUALITY METRICS")
    print("-" * 80)
    
    # Calculate distribution
    sizes = [len(c.get('review_ids', [])) for c in clusters]
    avg_size = sum(sizes) / len(sizes) if sizes else 0
    min_size = min(sizes) if sizes else 0
    max_size = max(sizes) if sizes else 0
    
    print(f"  Cluster Size Statistics:")
    print(f"    Average: {avg_size:.1f} reviews/cluster")
    print(f"    Range: {min_size} to {max_size} reviews")
    print(f"    Median: {sorted(sizes)[len(sizes)//2] if sizes else 0} reviews")
    
    # Size distribution
    small = sum(1 for s in sizes if s < 5)
    medium = sum(1 for s in sizes if 5 <= s < 20)
    large = sum(1 for s in sizes if 20 <= s < 100)
    huge = sum(1 for s in sizes if s >= 100)
    
    print(f"\n  Distribution:")
    print(f"    Small (<5):      {small:4} clusters ({small/len(clusters)*100:.1f}%)")
    print(f"    Medium (5-20):   {medium:4} clusters ({medium/len(clusters)*100:.1f}%)")
    print(f"    Large (20-100):  {large:4} clusters ({large/len(clusters)*100:.1f}%)")
    print(f"    Huge (100+):     {huge:4} clusters ({huge/len(clusters)*100:.1f}%)")
    
    # Quality assessment
    print(f"\n  Quality Assessment:")
    good_distribution = medium + large > len(clusters) * 0.5
    high_rca_rate = with_rca / len(clusters) > 0.9
    balanced_severity = severities.get('critical', 0) < len(clusters) * 0.3
    
    print(f"    ✓ Good cluster sizes: {'✅ PASS' if good_distribution else '⚠️  WARN'}")
    print(f"    ✓ High RCA rate: {'✅ PASS' if high_rca_rate else '⚠️  WARN'}")
    print(f"    ✓ Balanced severity: {'✅ PASS' if balanced_severity else '⚠️  WARN'}")
    
    # Sample RCA for detailed inspection
    print("\n\n🔍 SAMPLE RCA INSPECTION (First Cluster)")
    print("-" * 80)
    
    if sorted_clusters:
        cluster = sorted_clusters[0]
        print(f"Title: {cluster.get('title', 'N/A')}")
        print(f"Severity: {cluster.get('severity', 'N/A').upper()}")
        print(f"Evidence: {len(cluster.get('review_ids', []))} reviews")
        
        rca = cluster.get('root_cause_analysis', {})
        if rca:
            print(f"\nRoot Cause Analysis:")
            print(f"  Title: {rca.get('title', 'N/A')}")
            print(f"\n  Hypothesis:")
            print(f"    {rca.get('hypothesis', 'N/A')}")
            
            repro = rca.get('reproduction_steps', [])
            if repro:
                print(f"\n  Reproduction Steps:")
                for i, step in enumerate(repro, 1):
                    print(f"    {i}. {step}")
            
            fix = rca.get('suggested_fix', 'N/A')
            print(f"\n  Suggested Fix:")
            print(f"    {fix}")
            
            confidence = rca.get('confidence', 0)
            print(f"\n  Confidence: {confidence}%")
    
    # Export option
    print("\n\n💾 EXPORT OPTIONS")
    print("-" * 80)
    print(f"  Full JSON: curl {BACKEND_URL}/clusters > results.json")
    print(f"  CSV Export: (implement in frontend later)")
    
    print("\n" + "="*80)
    print()

if __name__ == "__main__":
    analyze_clusters()
