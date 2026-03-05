# Roast 🔥

**Turn app store reviews into engineering tickets — automatically.**

Roast ingests raw user reviews, clusters them by semantic similarity, runs LLM-powered Root Cause Analysis, and exports structured tickets straight to GitHub Issues or Linear.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI · Python 3.11 · SQLModel · ChromaDB |
| AI | Sentence-Transformers (`all-MiniLM-L6-v2`) · LLM (configurable) |
| Frontend | Next.js 14 (App Router) · TypeScript · Tailwind · TanStack Query |
| Infra | Shadow deployment · Drift monitoring · Adversarial detection |

---

## How it works

```
CSV Upload → Schema Detection → Noise Filter → Semantic Clustering
     → Severity Classification (CRITICAL / HIGH / MEDIUM / LOW)
     → LLM Summaries + RCA per cluster
     → Export to GitHub Issues / Linear / Markdown
```

1. **Upload** — drop any reviews CSV; auto-detects 13+ column formats
2. **Cluster** — ChromaDB groups semantically similar complaints
3. **Classify** — each cluster gets a severity + drift/regression flags
4. **Analyze** — background job generates 7-section RCA (hypothesis → fix → prevention)
5. **Export** — one-click ticket to GitHub Issues or Linear with full context

---

## Quick Start

```bash
# Backend
cd backend && python -m venv venv && .\venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # → localhost:8000

# Frontend
cd frontend && npm install
npm run dev                            # → localhost:3000
```

---

## Key API Routes

```
POST /api/upload            Upload reviews CSV
GET  /api/uploads           List all uploads
GET  /api/clusters          Get clusters for an upload
GET  /api/severity-summary  LLM-generated category summaries
GET  /health                Health check
```

---

## Production Features

- **Shadow Deployment** — runs v1/v2/v3 pipelines in parallel, compares drift
- **Adversarial Detection** — flags spam campaigns, coordinated bots, template attacks
- **Regression Detection** — Jaccard similarity tracks if a fixed bug resurfaces
- **RCA Engine** — async background job generates Root Cause Analysis for top CRITICAL/HIGH clusters
- **Structured Logging** — full request traceability with correlation IDs

---

## Deploy

**Frontend → Vercel**
```bash
NEXT_PUBLIC_API_URL=https://your-backend.com
```

**Backend → Railway / Render**
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

MIT License
