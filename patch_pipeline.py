import os

VENV_PATH = r"E:\BMSIT\Personal Ai projects\1 Internship-Resume Projects\5_Roast_google_reviews\backend\venv"
pipeline_path = os.path.join(VENV_PATH, "Lib", "site-packages", "roast_fast", "pipeline.py")

print(f"Patching noise filter in: {pipeline_path}")

# Read original, find similarity threshold, reduce it
with open(pipeline_path, 'r') as f:
    content = f.read()

# Find lines with similarity threshold (usually 0.7-0.8)
# Replace with more lenient 0.45
content = content.replace("0.75", "0.45").replace("0.7", "0.45").replace("0.8", "0.45")

with open(pipeline_path, 'w') as f:
    f.write(content)

print("✅ Noise filter relaxed: 0.75→0.45")
print("Now re-run: python a.py")
