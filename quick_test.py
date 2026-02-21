"""
Quick Test Script - Test backend with sample datasets
Uploads test CSV and shows AI analysis results
"""

import requests
import json
from pathlib import Path
import time

# Test configuration
BACKEND_URL = "http://localhost:8000"
TEST_FILES = {
    "100": "test_100_reviews.csv",
    "1k": "test_1k_reviews.csv", 
    "10k": "test_10k_reviews.csv",
    "100k": "test_100k_reviews.csv"
}

def test_backend(dataset_size="100"):
    """Test backend with specified dataset size"""
    
    filename = TEST_FILES.get(dataset_size)
    if not filename:
        print(f"❌ Invalid dataset size. Choose: {list(TEST_FILES.keys())}")
        return
    
    filepath = Path(filename)
    if not filepath.exists():
        print(f"❌ File not found: {filename}")
        print("Run: python split_dataset.py first")
        return
    
    print(f"\n{'='*70}")
    print(f"🔥 ROAST Backend Test - {dataset_size} Reviews")
    print(f"{'='*70}\n")
    print(f"📁 File: {filename} ({filepath.stat().st_size / 1024:.2f} KB)")
    print(f"🚀 Uploading to {BACKEND_URL}/test-upload...")
    
    # Check backend health
    try:
        health = requests.get(f"{BACKEND_URL}/health", timeout=5)
        if health.status_code != 200:
            print(f"❌ Backend not responding. Start it with: uvicorn app.main:app --reload")
            return
        print(f"✓ Backend is healthy: {health.json()}\n")
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to backend at {BACKEND_URL}")
        print("Start backend with: cd backend && uvicorn app.main:app --reload")
        return
    
    # Upload file
    start_time = time.time()
    
    with open(filepath, 'rb') as f:
        files = {'file': (filename, f, 'text/csv')}
        print(f"⏳ Processing (this may take a while)...")
        
        try:
            response = requests.post(
                f"{BACKEND_URL}/test-upload",
                files=files,
                timeout=300  # 5 minute timeout
            )
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                stats = result['stats']
                clusters = result['clusters']
                
                print(f"\n✅ SUCCESS! Processed in {elapsed:.2f} seconds")
                print(f"\n{'='*70}")
                print("📊 PROCESSING STATISTICS")
                print(f"{'='*70}")
                print(f"  Total Reviews:      {stats['processed']}")
                print(f"  Clusters Created:   {stats['new_issues']}")
                print(f"  Duplicates Merged:  {stats['merged']}")
                print(f"  AI Analyzed:        {stats['ai_analyzed']}")
                print(f"  AI Failed:          {stats['ai_failed']}")
                print(f"  Processing Time:    {stats['processing_time_ms']:.0f} ms")
                
                print(f"\n{'='*70}")
                print(f"🎯 TOP CLUSTERS (showing {len(clusters)} of {stats['new_issues']})")
                print(f"{'='*70}\n")
                
                for i, cluster in enumerate(clusters, 1):
                    print(f"[{i}] {cluster['title']}")
                    print(f"    Severity: {cluster['severity'].upper()}")
                    print(f"    Evidence: {cluster['evidence_count']} reviews")
                    print(f"    AI Status: {'✓ Analyzed' if cluster['ai_analyzed'] else '✗ Not Analyzed'}")
                    
                    if cluster['ai_analyzed'] and cluster['rca_title']:
                        print(f"\n    🔍 RCA Title: {cluster['rca_title']}")
                        if cluster['rca_hypothesis']:
                            print(f"    💡 Root Cause: {cluster['rca_hypothesis']}")
                        if cluster['rca_fix']:
                            print(f"    🔧 Suggested Fix: {cluster['rca_fix']}")
                    
                    print()
                
                # Save results to file
                output_file = f"test_results_{dataset_size}.json"
                with open(output_file, 'w') as f:
                    json.dump(result, f, indent=2)
                print(f"💾 Full results saved to: {output_file}")
                
                # Summary
                print(f"\n{'='*70}")
                print("🎓 ACCURACY CHECK")
                print(f"{'='*70}")
                print(f"  AI Success Rate:    {stats['ai_analyzed'] / stats['new_issues'] * 100:.1f}%")
                print(f"  Deduplication Rate: {stats['merged'] / stats['processed'] * 100:.1f}%")
                print(f"  Processing Speed:   {stats['processed'] / elapsed:.1f} reviews/sec")
                print()
                
            else:
                print(f"❌ Upload failed: {response.status_code}")
                print(response.text)
                
        except requests.exceptions.Timeout:
            print(f"❌ Request timeout after 5 minutes")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    import sys
    
    # Get dataset size from command line or default to 100
    size = sys.argv[1] if len(sys.argv) > 1 else "100"
    
    test_backend(size)
    
    print(f"\n{'='*70}")
    print("🔥 Test other datasets:")
    print(f"{'='*70}")
    print("  python quick_test.py 100    # 100 reviews (fast)")
    print("  python quick_test.py 1k     # 1,000 reviews")
    print("  python quick_test.py 10k    # 10,000 reviews")
    print("  python quick_test.py 100k   # 100,000 reviews (slow)")
    print()

print("\n" + "="*80)
print("  🚀 ROAST - Quick Backend Test")
print("="*80)

# Check backend
print("\n1️⃣  Checking backend connection...")
try:
    response = requests.get(f"{BACKEND_URL}/health", timeout=5)
    print(f"   ✓ Backend is running: {response.json()}")
except Exception as e:
    print(f"   ❌ Backend not running! Start it first.")
    exit(1)

# Check file
if not Path(TEST_FILE).exists():
    print(f"\n❌ File not found: {TEST_FILE}")
    print("   Run: python split_dataset.py first")
    exit(1)

print(f"\n2️⃣  Uploading {TEST_FILE}...")
print(f"   File size: {Path(TEST_FILE).stat().st_size / 1024:.1f} KB")

start_time = time.time()

try:
    with open(TEST_FILE, 'rb') as f:
        files = {'file': (TEST_FILE, f, 'text/csv')}
        response = requests.post(
            f"{BACKEND_URL}/test/upload",  # Using test endpoint (no auth required)
            files=files,
            timeout=120  # 2 minutes max
        )
    
    upload_time = time.time() - start_time
    
    if response.status_code == 200:
        result = response.json()
        print(f"\n   ✅ Upload successful! ({upload_time:.1f}s)")
        print(f"\n   Response:")
        print(json.dumps(result, indent=2))
        
        # Key metrics
        print(f"\n3️⃣  Processing Summary:")
        print(f"   • Processed: {result.get('processed', 0)} reviews")
        print(f"   • New Issues: {result.get('new_issues', 0)} clusters")
        print(f"   • Merged: {result.get('merged', 0)} duplicates")
        print(f"   • AI Analyzed: {result.get('ai_analyzed', 0)} RCAs")
        print(f"   • Failed: {result.get('ai_failed', 0)} errors")
        print(f"   • Time: {result.get('processing_time_ms', 0) / 1000:.1f}s")
        
    else:
        print(f"\n   ❌ Upload failed: {response.status_code}")
        print(f"   Error: {response.text}")
        exit(1)

except requests.exceptions.Timeout:
    print(f"\n   ⏱️  Timeout after {upload_time:.1f}s")
    print(f"   Backend might still be processing...")
except Exception as e:
    print(f"\n   ❌ Error: {e}")
    exit(1)

# Fetch clusters
print(f"\n4️⃣  Fetching clusters...")
try:
    response = requests.get(f"{BACKEND_URL}/clusters", timeout=10)
    clusters = response.json()
    
    print(f"   ✓ Found {len(clusters)} clusters")
    
    if clusters:
        print(f"\n5️⃣  Sample Clusters (Top 5):")
        print("   " + "-"*76)
        
        # Sort by evidence count
        sorted_clusters = sorted(
            clusters,
            key=lambda c: len(c.get('review_ids', [])),
            reverse=True
        )
        
        for i, cluster in enumerate(sorted_clusters[:5], 1):
            title = cluster.get('title', 'Unknown')
            severity = cluster.get('severity', 'unknown')
            evidence = len(cluster.get('review_ids', []))
            
            emoji = {
                'critical': '🔴',
                'high': '🟠',
                'medium': '🟡',
                'low': '🟢'
            }.get(severity, '⚪')
            
            print(f"\n   {i}. {emoji} {title[:65]}")
            print(f"      Severity: {severity.upper()} | Evidence: {evidence} reviews")
            
            rca = cluster.get('root_cause_analysis', {})
            if rca:
                print(f"      RCA: {rca.get('title', 'N/A')[:70]}")
                print(f"      Fix: {rca.get('suggested_fix', 'N/A')[:70]}...")
            else:
                print(f"      RCA: ❌ Not generated")
        
        # Quality check
        print(f"\n6️⃣  Quality Check:")
        print("   " + "-"*76)
        
        with_rca = sum(1 for c in clusters if c.get('root_cause_analysis'))
        rca_rate = with_rca / len(clusters) * 100 if clusters else 0
        
        print(f"   • RCA Coverage: {with_rca}/{len(clusters)} ({rca_rate:.1f}%)")
        print(f"     {'✅ EXCELLENT' if rca_rate > 90 else '⚠️  NEEDS IMPROVEMENT'}")
        
        avg_evidence = sum(len(c.get('review_ids', [])) for c in clusters) / len(clusters)
        print(f"\n   • Avg Evidence: {avg_evidence:.1f} reviews/cluster")
        print(f"     {'✅ GOOD' if 5 <= avg_evidence <= 50 else '⚠️  CHECK THRESHOLD'}")
        
        # Severity distribution
        from collections import Counter
        severities = Counter(c.get('severity', 'unknown') for c in clusters)
        critical_rate = severities.get('critical', 0) / len(clusters) * 100
        
        print(f"\n   • Critical Issues: {severities.get('critical', 0)} ({critical_rate:.1f}%)")
        print(f"     {'✅ BALANCED' if critical_rate < 30 else '⚠️  TOO MANY CRITICALS'}")
        
        print(f"\n7️⃣  Next Steps:")
        print("   " + "-"*76)
        print(f"   • View full analysis: python analyze_results.py")
        print(f"   • View in frontend: http://localhost:3000/dashboard")
        print(f"   • Test larger dataset: test_1k_reviews.csv")
        print(f"   • Export JSON: curl {BACKEND_URL}/clusters > results.json")
        
    else:
        print(f"\n   ⚠️  No clusters created - all reviews might be low quality")

except Exception as e:
    print(f"   ❌ Error fetching clusters: {e}")

print("\n" + "="*80)
print("  ✅ Quick test complete!")
print("="*80 + "\n")
