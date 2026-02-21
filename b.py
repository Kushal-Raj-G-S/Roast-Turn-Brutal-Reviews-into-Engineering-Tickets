# patch_indexer.py — FINAL: adds size() + full pipeline compatibility
import os
import sys

VENV_PATH = r"E:\BMSIT\Personal Ai projects\1 Internship-Resume Projects\5_Roast_google_reviews\backend\venv"
site_packages = os.path.join(VENV_PATH, "Lib", "site-packages")
indexer_path = os.path.join(site_packages, "roast_fast", "indexer.py")

print(f"✅ Patching indexer: {indexer_path}\n")

new_code = '''
import faiss
import numpy as np
from typing import Tuple


class FastIndexer:
    """FAISS IVF index with dynamic nlist + size tracking."""

    def __init__(self, dim: int = 384, nlist: int = 256):
        self.dim = dim
        self.nlist = nlist
        self.index = None
        self._ntotal = 0  # Track total indexed vectors

    def train(self, embeddings: np.ndarray):
        """Train with dynamic nlist adjustment."""
        n_samples = len(embeddings)
        actual_nlist = min(self.nlist, max(1, n_samples // 2))
        
        quantizer = faiss.IndexFlatL2(self.dim)
        self.index = faiss.IndexIVFFlat(quantizer, self.dim, actual_nlist)
        self.index.train(embeddings.astype(np.float32))
        print(f"FAISS: {n_samples} points → {actual_nlist} clusters")

    def add(self, embeddings: np.ndarray):
        """Add embeddings to index."""
        if self.index is None:
            self.train(embeddings)
        n_added = len(embeddings)
        self.index.add(embeddings.astype(np.float32))
        self._ntotal += n_added

    @property
    def size(self) -> int:
        """Return total number of indexed vectors (matches original API)."""
        return self._ntotal if self.index is not None else 0

    def search(self, query: np.ndarray, k: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        """Search for k nearest neighbors."""
        distances, indices = self.index.search(query.astype(np.float32), k)
        return distances, indices

    def reset(self):
        """Reset index."""
        self.index = None
        self._ntotal = 0
'''

with open(indexer_path, "w", encoding="utf-8") as f:
    f.write(new_code)

print(f"✅ Patched successfully!")
print(f"   ✓ FastIndexer class")
print(f"   ✓ Dynamic nlist")
print(f"   ✓ size property (fixes pipeline.py)")
print()
print("Now run: python a.py")
