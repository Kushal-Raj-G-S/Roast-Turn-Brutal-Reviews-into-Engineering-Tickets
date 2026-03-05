# Roast 🔥

**Turn app store reviews into engineering tickets — automatically.**

Roast ingests raw user reviews, clusters them by semantic similarity, runs LLM-powered Root Cause Analysis, and exports structured tickets straight to GitHub Issues or Linear. Built for mobile teams who are drowning in feedback but starved for signal.

---

## ☕ Support the Developer

If you find Roast useful, consider supporting its development!

[![Buy Me A Coffee](https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png)](https://buymeacoffee.com/kushal.raj.gs)

Your support helps me:
- 🚀 Continue developing new features
- 🐛 Fix bugs and improve performance
- 📱 Add support for more platforms
- 🤖 Enhance the AI analysis pipeline

Every coffee makes a difference! ☕💻

---

## The Problem

Product teams get thousands of app store reviews. Most tooling just shows you a star rating. Roast goes further — it reads every review, groups them by **what's actually broken**, assigns severity, and drafts a ready-to-file bug report with a machine-generated root cause hypothesis.

No manual tagging. No spreadsheets. Just actionable tickets.

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

1. **Upload** — drop any reviews CSV; schema intelligence auto-detects 13+ column formats (Play Store, App Store, custom exports)
2. **Filter** — noise filter strips "great app!" generics; adversarial detector removes coordinated spam and bot campaigns
3. **Cluster** — ChromaDB embeds and groups semantically similar complaints into named issue clusters
4. **Classify** — CRITICAL / HIGH / MEDIUM / LOW severity assigned per cluster; regression and spike flags added automatically
5. **Analyze** — async background job runs LLM over each top cluster, producing a structured 7-section Root Cause Analysis: hypothesis → affected surface → reproduction steps → diagnostic checklist → fix → prevention → notes
6. **Export** — one-click ticket to GitHub Issues or Linear; markdown includes RCA, sample user quotes, affected versions/devices, and suggested labels

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

> Requires Python 3.11+ and Node 18+. Backend expects an `LLM_API_KEY` env var for RCA generation.

---

## Key API Routes

```
POST /api/upload            Upload reviews CSV — starts async processing pipeline
GET  /api/uploads           List all uploads with status and cluster counts
GET  /api/clusters          Get all clusters for an upload (severity, RCA, regression flags)
GET  /api/severity-summary  LLM-generated category summaries (CRITICAL/HIGH/MEDIUM/LOW)
GET  /health                Health check
```

---

## Production Features

### AI & Analysis
- **Semantic Clustering** — `all-MiniLM-L6-v2` embeddings + ChromaDB for fast nearest-neighbour grouping
- **RCA Engine** — 7-section structured Root Cause Analysis generated async for all CRITICAL/HIGH clusters
- **Spike Detection** — flags statistical volume spikes (1.5σ above baseline) in real time
- **Adversarial Detection** — identifies spam campaigns, coordinated bot reviews, and template injection attacks

### Reliability
- **Shadow Deployment** — v1/v2/v3 pipelines run in parallel; Jaccard similarity compares outputs to catch regressions before they ship
- **Regression Detection** — tracks if a previously-fixed cluster resurfaces across new upload batches
- **Drift Monitoring** — alerts when cluster distribution shifts significantly between uploads

### Engineering
- **Structured Logging** — full request traceability with correlation IDs across every pipeline stage
- **Async Workers** — LLM calls run in background tasks; upload response is instant
- **Schema Intelligence** — handles messy real-world CSVs with missing/renamed/reordered columns

---

## Ticket Export

The export modal intelligently branches based on **cluster type**:

| Cluster Type | Behaviour |
|---|---|
| `positive` | Routes as product signal — not a bug ticket |
| `feature_request` | Routes to PM backlog with user voice quotes |
| `complaint` | Routes to UX team with impact assessment |
| `crash / performance / login / payment` | Full 7-section RCA bug report |

Each export includes: severity, signal strength, affected versions & devices, sample user reviews, and auto-generated labels.

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

## Project Structure

```
/backend
  app/
    api/          FastAPI route handlers
    services/     Business logic (clustering, RCA, severity)
    models/       SQLModel DB schemas
    workers/      Async background task runners
  src/            Domain entities + infrastructure layer
/frontend
  src/
    app/          Next.js App Router pages
    components/   UI components incl. TicketExportModal
/dataset          Sample Google Play review CSVs for testing
```

---

MIT License
