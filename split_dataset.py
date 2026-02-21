"""
Dataset Splitter - Create test datasets of different sizes
"""
import pandas as pd
import os
from pathlib import Path

print("\n" + "="*60)
print("  🔥 ROAST - Dataset Splitter")
print("="*60 + "\n")

# Load the large dataset
print("📂 Loading large dataset...")
df = pd.read_csv('chatgpt_reviews.csv')
total_reviews = len(df)

print(f"✓ Loaded {total_reviews:,} reviews")
print(f"✓ Columns: {list(df.columns)}")
print(f"✓ File size: {os.path.getsize('chatgpt_reviews.csv') / (1024*1024):.2f} MB\n")

# Show sample
print("📝 Sample review:")
print(f"   {df.iloc[0].to_dict()}\n")

# Define split sizes
splits = {
    'test_100_reviews.csv': 100,
    'test_1k_reviews.csv': 1000,
    'test_10k_reviews.csv': 10000,
    'test_100k_reviews.csv': 100000,
}

print("🔪 Creating split datasets...\n")

results = []

for filename, size in splits.items():
    if size > total_reviews:
        print(f"⚠️  {filename}: SKIPPED (requested {size:,} > available {total_reviews:,})")
        continue
    
    # Sample randomly with seed for reproducibility
    sample_df = df.sample(n=size, random_state=42)
    
    # Save to CSV
    sample_df.to_csv(filename, index=False)
    
    file_size = os.path.getsize(filename) / 1024  # KB
    
    print(f"✓ {filename}")
    print(f"  - Reviews: {size:,}")
    print(f"  - File size: {file_size:.2f} KB")
    
    # Analyze content
    if 'rating' in sample_df.columns:
        avg_rating = sample_df['rating'].mean()
        print(f"  - Avg rating: {avg_rating:.2f}/5")
    
    if 'content' in sample_df.columns or 'review' in sample_df.columns:
        content_col = 'content' if 'content' in sample_df.columns else 'review'
        avg_length = sample_df[content_col].str.len().mean()
        print(f"  - Avg review length: {avg_length:.0f} chars")
    
    print()
    
    results.append({
        'file': filename,
        'reviews': size,
        'size_kb': file_size
    })

# Print summary
print("\n" + "="*60)
print("  ✅ SPLIT COMPLETE")
print("="*60 + "\n")

print("📊 Summary:")
for r in results:
    print(f"  • {r['file']}: {r['reviews']:,} reviews ({r['size_kb']:.1f} KB)")

print("\n🎯 Expected Backend Performance:")
print("  • 100 reviews:   ~1-2 seconds   → ~5-10 clusters")
print("  • 1K reviews:    ~5-10 seconds  → ~30-50 clusters")
print("  • 10K reviews:   ~30-60 seconds → ~100-200 clusters")
print("  • 100K reviews:  ~5-10 minutes  → ~500-1000 clusters")

print("\n💡 Tip: Start with test_100_reviews.csv to verify accuracy!")
