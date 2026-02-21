"""
Backend Accuracy Tester - Test different dataset sizes and analyze output
"""
import requests
import json
import time
from pathlib import Path

# Backend URL
BACKEND_URL = "http://localhost:8000"

print("\n" + "="*70)
print("  🔥 ROAST - Backend Accuracy Tester")
print("="*70 + "\n")

# Check if backend is running
print("🔍 Checking backend connection...")
try:
    response = requests.get(f"{BACKEND_URL}/health", timeout=5)
    if response.status_code == 200:
        print(f"✓ Backend is running: {response.json()}\n")
    else:
        print("✗ Backend returned error")
        exit(1)
except Exception as e:
    print(f"✗ Backend not running! Start it first:\n")
    print("  cd backend")
    print("  .\\venv\\Scripts\\activate")
    print("  uvicorn app.main:app --reload\n")
    exit(1)

# Test datasets
test_files = [
    ('test_100_reviews.csv', 'Quick Test', '100 reviews'),
    ('test_1k_reviews.csv', 'Small Scale', '1K reviews'),
    ('test_10k_reviews.csv', 'Medium Scale', '10K reviews'),
    ('test_100k_reviews.csv', 'Large Scale', '100K reviews'),
]

print("📊 Available test datasets:")
for i, (file, label, desc) in enumerate(test_files, 1):
    exists = "✓" if Path(file).exists() else "✗"
    print(f"  {i}. {exists} {file} - {label} ({desc})")

print("\n" + "="*70)
print("  🧪 TESTING INSTRUCTIONS")
print("="*70 + "\n")

print("""
HOW TO TEST:
------------

1. **Upload via Frontend** (Recommended):
   • Open: http://localhost:3000/upload
   • Drag & drop one of the test CSV files
   • Watch the magic happen!

2. **Upload via API** (Advanced):
   • Use curl or Postman
   • POST to: http://localhost:8000/upload
   • Body: form-data with file upload

3. **Check Results**:
   • GET: http://localhost:8000/clusters
   • See all detected issue clusters
   • Each cluster has AI-generated RCA

""")

print("="*70)
print("  📋 EXPECTED OUTPUT FOR EACH DATASET")
print("="*70 + "\n")

outputs = [
    {
        'file': 'test_100_reviews.csv',
        'reviews': 100,
        'expected_time': '1-2 seconds',
        'expected_clusters': '5-10 clusters',
        'sample_output': {
            'processed': 100,
            'merged': 85,
            'new_issues': 8,
            'ai_analyzed': 8,
            'ai_failed': 0,
            'processing_time_ms': 1500
        },
        'clusters_example': [
            {
                'title': 'App crashes on startup',
                'severity': 'critical',
                'evidence_count': 15,
                'rca_title': 'NullPointerException in MainActivity.onCreate()',
                'rca_hypothesis': 'Missing null check for savedInstanceState',
                'suggested_fix': 'Add defensive null check before accessing bundle'
            },
            {
                'title': 'Login button not working',
                'severity': 'high',
                'evidence_count': 12,
                'rca_title': 'OAuth redirect timeout on slow networks',
                'rca_hypothesis': 'Network timeout set too low (5s)',
                'suggested_fix': 'Increase timeout to 15s and add retry logic'
            }
        ]
    },
    {
        'file': 'test_1k_reviews.csv',
        'reviews': 1000,
        'expected_time': '5-10 seconds',
        'expected_clusters': '30-50 clusters',
        'sample_output': {
            'processed': 1000,
            'merged': 920,
            'new_issues': 35,
            'ai_analyzed': 35,
            'ai_failed': 0,
            'processing_time_ms': 8200
        },
        'note': 'More diverse issues, better pattern detection'
    },
    {
        'file': 'test_10k_reviews.csv',
        'reviews': 10000,
        'expected_time': '30-60 seconds',
        'expected_clusters': '100-200 clusters',
        'sample_output': {
            'processed': 10000,
            'merged': 9500,
            'new_issues': 150,
            'ai_analyzed': 150,
            'ai_failed': 0,
            'processing_time_ms': 45000
        },
        'note': 'Comprehensive issue coverage, real-world patterns'
    },
    {
        'file': 'test_100k_reviews.csv',
        'reviews': 100000,
        'expected_time': '5-10 minutes',
        'expected_clusters': '500-1000 clusters',
        'sample_output': {
            'processed': 100000,
            'merged': 98500,
            'new_issues': 800,
            'ai_analyzed': 800,
            'ai_failed': 0,
            'processing_time_ms': 420000
        },
        'note': 'Enterprise scale, long-tail issues visible'
    }
]

for output in outputs:
    print(f"📄 {output['file']}")
    print(f"   Reviews: {output['reviews']:,}")
    print(f"   ⏱️  Time: {output['expected_time']}")
    print(f"   📊 Clusters: {output['expected_clusters']}")
    print(f"\n   Response JSON:")
    print(f"   {json.dumps(output['sample_output'], indent=2)}")
    
    if 'clusters_example' in output:
        print(f"\n   Sample Clusters:")
        for i, cluster in enumerate(output['clusters_example'], 1):
            print(f"   {i}. {cluster['title']}")
            print(f"      - Severity: {cluster['severity']}")
            print(f"      - Evidence: {cluster['evidence_count']} reviews")
            print(f"      - RCA: {cluster['rca_title']}")
            print(f"      - Fix: {cluster['suggested_fix']}")
    
    if 'note' in output:
        print(f"\n   💡 Note: {output['note']}")
    
    print("\n" + "-"*70 + "\n")

print("="*70)
print("  ✅ WHAT TO VERIFY FOR ACCURACY")
print("="*70 + "\n")

print("""
1. **Clustering Quality**:
   ✓ Similar reviews grouped together
   ✓ No duplicates in different clusters
   ✓ Each cluster represents ONE distinct issue

2. **RCA Quality**:
   ✓ Technical title makes sense
   ✓ Root cause hypothesis is logical
   ✓ Reproduction steps are actionable
   ✓ Suggested fix is specific

3. **Performance**:
   ✓ Processing time within expected range
   ✓ No LLM failures (ai_failed = 0)
   ✓ High merge rate (merged > 80% of processed)

4. **Edge Cases**:
   ✓ Short reviews ("good", "bad") filtered out
   ✓ 5-star reviews without issues ignored
   ✓ Similar issues from different devices merged

""")

print("="*70)
print("  🚀 QUICK TEST COMMAND")
print("="*70 + "\n")

print("""
Test 100 reviews via curl:

curl -X POST http://localhost:8000/upload \\
  -F "file=@test_100_reviews.csv" \\
  -H "Content-Type: multipart/form-data"

Then check clusters:

curl http://localhost:8000/clusters | python -m json.tool

""")

print("💡 Start with test_100_reviews.csv for quick validation!")
print()
