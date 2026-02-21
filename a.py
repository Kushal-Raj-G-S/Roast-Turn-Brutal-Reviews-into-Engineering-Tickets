# ================================================================
# test_roast_fast.py
# Test roast-fast on your real ChatGPT Play Store reviews dataset
# Run: python test_roast_fast.py
# ================================================================

import time
import pandas as pd

# ----------------------------------------------------------------
# 1. Load your CSV
# ----------------------------------------------------------------
CSV_PATH = "test_1k_reviews.csv"   # <-- put the CSV in same folder

print("Loading CSV...")
df = pd.read_csv(CSV_PATH)
print(f"Shape    : {df.shape}")
print(f"Columns  : {list(df.columns)}")
print(f"Sample review: {df['content'].iloc[3][:80]}...")
print()

# ----------------------------------------------------------------
# 2. Run roast-fast
# ----------------------------------------------------------------
print("Importing roast-fast...")
from roast_fast import process_reviews

print("Running process_reviews()...\n")
t0 = time.perf_counter()

result = process_reviews(
    df,
    text_col="content",     # your review text column
    rating_col="score",     # your rating column (1-5)
    threshold=0.80,         # cosine similarity to merge clusters
    batch_size=512,         # lower = less RAM, tune up if you have GPU
    min_length=5,           # skip very short reviews like "ok", "nice"
)

elapsed = time.perf_counter() - t0

# ----------------------------------------------------------------
# 3. Print results
# ----------------------------------------------------------------
s = result["stats"]

print("=" * 55)
print("  roast-fast - RESULTS ON YOUR REAL DATASET")
print("=" * 55)
print(f"  Total reviews     : {s['total_reviews']:>8,}")
print(f"  Processed         : {s['processed']:>8,}  (after noise filter)")
print(f"  Clusters found    : {s['clusters_found']:>8,}")
print(f"  Reviews merged    : {s['merged']:>8,}")
print()
print(f"  Filter time       : {s['filter_time_s']:>8.3f}s")
print(f"  Embed time        : {s['embed_time_s']:>8.3f}s")
print(f"  Cluster time      : {s['cluster_time_s']:>8.3f}s")
print(f"  ------------------------------------------")
print(f"  TOTAL TIME        : {s['total_time_s']:>8.3f}s")
print(f"  Throughput        : {s['throughput_rps']:>8,.0f} reviews/sec")
print("=" * 55)
print(f"  {'✅ Done in under 60s!' if elapsed < 60 else '❌ Took more than 60s'}")
print("=" * 55)

# ----------------------------------------------------------------
# 4. Print top clusters (actual issues found)
# ----------------------------------------------------------------
print("\nTop 10 clusters found in your reviews:\n")
for i, cluster in enumerate(result["clusters"][:10]):
    print(f"  #{i+1:02d}  size={cluster['size']:>4}  →  {cluster['sample_reviews'][0][:70]}")

# ----------------------------------------------------------------
# 5. Show some interesting clusters (complaints only)
# ----------------------------------------------------------------
print("\n--- Potential complaints / issues ---")
complaint_keywords = [
    "crash", "broken", "bug", "slow", "not work", "error",
    "fix", "problem", "worst", "bad", "useless", "fail",
    "login", "image", "ban", "restricted", "limit", "paid"
]

complaint_clusters = []
for c in result["clusters"]:
    text = c["sample_reviews"][0].lower()
    if any(kw in text for kw in complaint_keywords):
        complaint_clusters.append(c)

print(f"Found {len(complaint_clusters)} complaint clusters:\n")
for i, c in enumerate(complaint_clusters[:10]):
    print(f"  #{i+1:02d}  size={c['size']:>4}  →  {c['sample_reviews'][0][:75]}")

# ----------------------------------------------------------------
# 6. Export clusters to CSV
# ----------------------------------------------------------------
out_rows = []
for c in result["clusters"]:
    out_rows.append({
        "cluster_id":    c["id"],
        "size":          c["size"],
        "sample_review": c["sample_reviews"][0],
    })

out_df = pd.DataFrame(out_rows)
out_df.to_csv("clusters_output.csv", index=False)
print(f"\n✅ Clusters saved to clusters_output.csv ({len(out_df)} clusters)")
print(f"   Total time: {elapsed:.3f}s")
